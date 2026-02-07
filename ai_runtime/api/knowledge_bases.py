"""
Knowledge Bases API Endpoints
Handles HTTP requests for knowledge base operations
"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from uuid import UUID

from core.models.knowledge_base import (
    CreateKnowledgeBaseRequest,
    UpdateKnowledgeBaseRequest,
    KnowledgeBaseResponse,
    KnowledgeBaseWithStats,
    ListKnowledgeBasesResponse,
    ListDocumentsResponse,
    AccessLevel,
)
from core.services.knowledge_base_service import KnowledgeBaseService
from core.services.document_service import DocumentService
from core.dependencies import (
    get_current_tenant_id,
    get_current_user_id,
    get_kb_service,
    get_document_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/knowledge-bases", tags=["knowledge-bases"])


@router.post("", response_model=KnowledgeBaseResponse, status_code=201)
async def create_knowledge_base(
    request: CreateKnowledgeBaseRequest,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
    http_request: Request = None,
):
    """
    创建知识库

    - **name**: 知识库名称（必填）
    - **description**: 知识库描述（可选）
    - **access_level**: 访问权限 (tenant/user)
    - **metadata**: 额外元数据（可选）
    """
    try:
        ip_address = http_request.client.host if http_request and http_request.client else None
        user_agent = http_request.headers.get("user-agent") if http_request and http_request.headers else None

        kb = await kb_service.create_knowledge_base(
            tenant_id=tenant_id,
            request=request,
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return kb

    except Exception as e:
        logger.error(f"Failed to create knowledge base: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{kb_id}", response_model=KnowledgeBaseWithStats)
async def get_knowledge_base(
    kb_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
):
    """
    获取知识库详情（带统计信息）

    返回知识库信息及其包含的文档数量
    """
    try:
        kb = await kb_service.get_knowledge_base_with_stats(
            kb_id=kb_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        if not kb:
            raise HTTPException(status_code=404, detail="Knowledge base not found")

        return kb

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get knowledge base: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{kb_id}", response_model=KnowledgeBaseResponse)
async def update_knowledge_base(
    kb_id: str,
    request: UpdateKnowledgeBaseRequest,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
    http_request: Request = None,
):
    """
    更新知识库

    - **name**: 新的知识库名称（可选）
    - **description**: 新的知识库描述（可选）
    - **metadata**: 新的元数据（可选）

    注意：access_level 创建后不可修改
    """
    try:
        ip_address = http_request.client.host if http_request and http_request.client else None
        user_agent = http_request.headers.get("user-agent") if http_request and http_request.headers else None

        kb = await kb_service.update_knowledge_base(
            kb_id=kb_id,
            tenant_id=tenant_id,
            request=request,
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        if not kb:
            raise HTTPException(status_code=404, detail="Knowledge base not found")

        return kb

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update knowledge base: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{kb_id}", status_code=204)
async def delete_knowledge_base(
    kb_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
    http_request: Request = None,
):
    """
    删除知识库

    警告：此操作将级联删除知识库中的所有文档，且不可恢复！
    """
    try:
        ip_address = http_request.client.host if http_request and http_request.client else None
        user_agent = http_request.headers.get("user-agent") if http_request and http_request.headers else None

        success = await kb_service.delete_knowledge_base(
            kb_id=kb_id,
            tenant_id=tenant_id,
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        if not success:
            raise HTTPException(status_code=404, detail="Knowledge base not found")

        return None

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete knowledge base: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=ListKnowledgeBasesResponse)
async def list_knowledge_bases(
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
    access_level: Optional[AccessLevel] = Query(None, description="筛选访问级别"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
):
    """
    列出知识库（分页）

    返回知识库列表，每个知识库包含文档数量统计
    """
    try:
        result = await kb_service.list_knowledge_bases(
            tenant_id=tenant_id,
            user_id=user_id,
            access_level=access_level,
            page=page,
            page_size=page_size,
        )

        return result

    except Exception as e:
        logger.error(f"Failed to list knowledge bases: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{kb_id}/documents", response_model=ListDocumentsResponse)
async def list_knowledge_base_documents(
    kb_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    document_service: DocumentService = Depends(get_document_service),
):
    """
    列出知识库中的文档（分页）

    返回指定知识库中的所有文档
    """
    try:
        result = await document_service.list_documents(
            tenant_id=tenant_id,
            user_id=user_id,
            knowledge_base_id=kb_id,
            page=page,
            page_size=page_size,
        )

        return result

    except Exception as e:
        logger.error(f"Failed to list documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{kb_id}/stats", response_model=KnowledgeBaseWithStats)
async def get_knowledge_base_stats(
    kb_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
):
    """
    获取知识库统计信息

    返回知识库的详细统计信息，包括文档数量等
    """
    try:
        stats = await kb_service.get_knowledge_base_with_stats(
            kb_id=kb_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        if not stats:
            raise HTTPException(status_code=404, detail="Knowledge base not found")

        return stats

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get knowledge base stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
