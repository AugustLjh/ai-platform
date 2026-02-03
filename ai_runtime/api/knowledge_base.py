"""
Knowledge Base API Routes
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query

from core.models.knowledge_base import (
    CreateDocumentRequest,
    UpdateDocumentRequest,
    DocumentResponse,
    ListDocumentsResponse,
    BatchCreateRequest,
    BatchCreateResponse,
    SearchDocumentsRequest,
    SearchDocumentsResponse,
    SearchResult,
    SourceType,
    AccessLevel,
)
from core.services.knowledge_base import KnowledgeBaseService
from core.dependencies import (
    get_kb_service,
    get_current_tenant_id,
    get_current_user_id,
    get_current_request_context,
)
from core.quota import QuotaError, convert_quota_error_to_http_exception


logger = logging.getLogger(__name__)

# 创建路由器
router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge-base"])


# ===== API端点 =====


@router.post("/documents", response_model=DocumentResponse, status_code=201)
async def create_document(
    request: CreateDocumentRequest,
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
    context: dict = Depends(get_current_request_context),
):
    """
    创建文档

    - **title**: 文档标题
    - **content**: 文档内容
    - **source**: 来源（可选）
    - **source_type**: 来源类型 (manual/file/url/batch)
    - **access_level**: 访问权限 (tenant/user)
    - **metadata**: 额外元数据（可选）
    - **auto_index**: 是否自动生成向量索引
    """
    try:
        doc = await kb_service.create_document(tenant_id, user_id, request, context)
        return DocumentResponse(**doc.to_dict())
    except QuotaError as e:
        raise convert_quota_error_to_http_exception(e)
    except Exception as e:
        logger.error(f"Failed to create document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str,
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
):
    """
    获取单个文档

    - **document_id**: 文档ID
    """
    doc = await kb_service.get_document(document_id, tenant_id, user_id)

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found or access denied")

    return DocumentResponse(**doc.to_dict())


@router.put("/documents/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: str,
    request: UpdateDocumentRequest,
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
):
    """
    更新文档

    - **document_id**: 文档ID
    - **title**: 新标题（可选）
    - **content**: 新内容（可选）
    - **source**: 新来源（可选）
    - **metadata**: 新元数据（可选）
    - **re_index**: 是否重新生成索引
    """
    doc = await kb_service.update_document(document_id, tenant_id, user_id, request)

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found or access denied")

    return DocumentResponse(**doc.to_dict())


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(
    document_id: str,
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
):
    """
    删除文档

    - **document_id**: 文档ID
    """
    success = await kb_service.delete_document(document_id, tenant_id, user_id)

    if not success:
        raise HTTPException(status_code=404, detail="Document not found or access denied")

    return None


@router.get("/documents", response_model=ListDocumentsResponse)
async def list_documents(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    access_level: Optional[AccessLevel] = Query(None, description="筛选访问级别"),
    source_type: Optional[SourceType] = Query(None, description="筛选来源类型"),
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
):
    """
    列出文档（分页）

    - **page**: 页码（从1开始）
    - **page_size**: 每页数量（1-100）
    - **access_level**: 筛选访问级别（可选）
    - **source_type**: 筛选来源类型（可选）
    """
    docs, total = await kb_service.list_documents(
        tenant_id=tenant_id,
        user_id=user_id,
        access_level=access_level,
        source_type=source_type,
        page=page,
        page_size=page_size,
    )

    return ListDocumentsResponse(
        documents=[DocumentResponse(**doc.to_dict()) for doc in docs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/documents/search", response_model=SearchDocumentsResponse)
async def search_documents(
    request: SearchDocumentsRequest,
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
):
    """
    向量语义搜索文档

    - **query**: 搜索查询文本
    - **top_k**: 返回结果数量（1-50）
    - **access_level**: 筛选访问级别（可选）
    - **source_type**: 筛选来源类型（可选）
    """
    results = await kb_service.search_documents(
        tenant_id=tenant_id,
        user_id=user_id,
        query=request.query,
        top_k=request.top_k,
        access_level=request.access_level,
        source_type=request.source_type,
    )

    return SearchDocumentsResponse(
        results=[
            SearchResult(
                document=DocumentResponse(**doc.to_dict()),
                score=score,
            )
            for doc, score in results
        ],
        query=request.query,
        total=len(results),
    )


@router.post("/documents/upload", response_model=DocumentResponse, status_code=201)
async def upload_file(
    file: UploadFile = File(..., description="上传的文件"),
    access_level: AccessLevel = Form(AccessLevel.TENANT, description="访问权限"),
    auto_index: bool = Form(True, description="是否自动索引"),
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
):
    """
    上传文件并创建文档

    支持的文件类型：
    - 文本文件：.txt
    - Markdown：.md
    - PDF：.pdf
    - HTML：.html, .htm

    - **file**: 上传的文件
    - **access_level**: 访问权限 (tenant/user)
    - **auto_index**: 是否自动生成向量索引
    """
    try:
        doc = await kb_service.upload_file(
            tenant_id=tenant_id,
            user_id=user_id,
            file=file,
            access_level=access_level,
            auto_index=auto_index,
        )
        return DocumentResponse(**doc.to_dict())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to upload file: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/documents/from-url", response_model=DocumentResponse, status_code=201)
async def create_from_url(
    url: str = Form(..., description="目标URL"),
    access_level: AccessLevel = Form(AccessLevel.TENANT, description="访问权限"),
    auto_index: bool = Form(True, description="是否自动索引"),
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
):
    """
    从URL抓取内容并创建文档

    - **url**: 目标URL
    - **access_level**: 访问权限 (tenant/user)
    - **auto_index**: 是否自动生成向量索引
    """
    try:
        doc = await kb_service.create_from_url(
            tenant_id=tenant_id,
            user_id=user_id,
            url=url,
            access_level=access_level,
            auto_index=auto_index,
        )
        return DocumentResponse(**doc.to_dict())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create from URL: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/documents/batch", response_model=BatchCreateResponse)
async def batch_create_documents(
    request: BatchCreateRequest,
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
):
    """
    批量创建文档

    - **documents**: 文档列表（最多100个）

    返回每个文档的创建结果，包括成功/失败状态
    """
    results = await kb_service.batch_create_documents(
        tenant_id=tenant_id,
        user_id=user_id,
        requests=request.documents,
    )

    success_count = sum(1 for r in results if r["success"])
    failed_count = len(results) - success_count

    return BatchCreateResponse(
        success_count=success_count,
        failed_count=failed_count,
        results=results,
    )


# ===== 统计和管理端点 =====


@router.get("/stats")
async def get_knowledge_base_stats(
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
):
    """
    获取知识库统计信息

    返回文档数量、索引状态等统计数据
    """
    # 获取全部文档（不分页）
    all_docs, total = await kb_service.list_documents(
        tenant_id=tenant_id,
        user_id=user_id,
        page=1,
        page_size=1000000,  # 大数字获取所有
    )

    indexed_count = sum(1 for doc in all_docs if doc.indexed)

    # 按来源类型统计
    by_source_type = {}
    for doc in all_docs:
        source_type = doc.source_type.value
        by_source_type[source_type] = by_source_type.get(source_type, 0) + 1

    # 按访问级别统计
    by_access_level = {}
    for doc in all_docs:
        access_level = doc.access_level.value
        by_access_level[access_level] = by_access_level.get(access_level, 0) + 1

    return {
        "total_documents": total,
        "indexed_documents": indexed_count,
        "unindexed_documents": total - indexed_count,
        "by_source_type": by_source_type,
        "by_access_level": by_access_level,
    }
