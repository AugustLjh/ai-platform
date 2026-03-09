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
    DocumentResponse,
    AccessLevel,
    IndexingSettings,
    IndexingSettingsUpdate,
    RetrievalSettings,
    RetrievalSettingsUpdate,
    AIGovernanceSettings,
    AIGovernanceSettingsUpdate,
    RetrievalTestRequest,
    RetrievalTestResponse,
    RetrievalTestResult,
    RetrievalTestSetCreateRequest,
    RetrievalTestSetUpdateRequest,
    RetrievalTestSetResponse,
    RetrievalEvaluationRunRequest,
    RetrievalEvaluationRunResponse,
    RetrievalEvaluationFeedbackRequest,
    RetrievalEvaluationApplyConfigResponse,
    DocumentSegment,
)
from core.services.knowledge_base_service import KnowledgeBaseService
from core.services.document_service import DocumentService
from core.services.retrieval_evaluation_service import RetrievalEvaluationService
from core.dependencies import (
    get_current_tenant_id,
    get_current_user_id,
    get_kb_service,
    get_document_service,
    get_retrieval_eval_service,
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


@router.get("/{kb_id}/indexing-settings", response_model=IndexingSettings)
async def get_indexing_settings(
    kb_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
):
    """获取知识库索引设置"""
    try:
        settings = await kb_service.get_indexing_settings(
            kb_id=kb_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        if settings is None:
            raise HTTPException(status_code=404, detail="Knowledge base not found")

        return IndexingSettings(**settings)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get indexing settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{kb_id}/indexing-settings", response_model=IndexingSettings)
async def update_indexing_settings(
    kb_id: str,
    request: IndexingSettingsUpdate,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
):
    """更新知识库索引设置"""
    try:
        settings = await kb_service.update_indexing_settings(
            kb_id=kb_id,
            tenant_id=tenant_id,
            user_id=user_id,
            updates=request.dict(exclude_unset=True),
        )

        if settings is None:
            raise HTTPException(status_code=404, detail="Knowledge base not found")

        return IndexingSettings(**settings)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update indexing settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{kb_id}/retrieval-settings", response_model=RetrievalSettings)
async def get_retrieval_settings(
    kb_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
):
    """获取知识库检索设置"""
    try:
        settings = await kb_service.get_retrieval_settings(
            kb_id=kb_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        if settings is None:
            raise HTTPException(status_code=404, detail="Knowledge base not found")

        return RetrievalSettings(**settings)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get retrieval settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{kb_id}/retrieval-settings", response_model=RetrievalSettings)
async def update_retrieval_settings(
    kb_id: str,
    request: RetrievalSettingsUpdate,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
):
    """更新知识库检索设置"""
    try:
        settings = await kb_service.update_retrieval_settings(
            kb_id=kb_id,
            tenant_id=tenant_id,
            user_id=user_id,
            updates=request.dict(exclude_unset=True),
        )

        if settings is None:
            raise HTTPException(status_code=404, detail="Knowledge base not found")

        return RetrievalSettings(**settings)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update retrieval settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{kb_id}/governance-settings", response_model=AIGovernanceSettings)
async def get_governance_settings(
    kb_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
):
    """获取知识库 AI 治理配置"""
    try:
        settings = await kb_service.get_governance_settings(
            kb_id=kb_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        if settings is None:
            raise HTTPException(status_code=404, detail="Knowledge base not found")

        return AIGovernanceSettings(**settings)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get governance settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{kb_id}/governance-settings", response_model=AIGovernanceSettings)
async def update_governance_settings(
    kb_id: str,
    request: AIGovernanceSettingsUpdate,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
):
    """更新知识库 AI 治理配置"""
    try:
        settings = await kb_service.update_governance_settings(
            kb_id=kb_id,
            tenant_id=tenant_id,
            user_id=user_id,
            updates=request.dict(exclude_unset=True),
        )

        if settings is None:
            raise HTTPException(status_code=404, detail="Knowledge base not found")

        return AIGovernanceSettings(**settings)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update governance settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{kb_id}/retrieval-test", response_model=RetrievalTestResponse)
async def retrieval_test(
    kb_id: str,
    request: RetrievalTestRequest,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
    kb_service: KnowledgeBaseService = Depends(get_kb_service),
    document_service: DocumentService = Depends(get_document_service),
):
    """执行知识库召回测试并返回命中文档及匹配分段"""
    try:
        settings = await kb_service.get_retrieval_settings(
            kb_id=kb_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        if settings is None:
            raise HTTPException(status_code=404, detail="Knowledge base not found")

        effective_top_k = int(request.top_k or settings.get("top_k") or 5)
        effective_threshold = float(
            request.score_threshold
            if request.score_threshold is not None
            else settings.get("score_threshold") or 0.0
        )

        results = await document_service.search_documents(
            tenant_id=tenant_id,
            user_id=user_id,
            query=request.query,
            top_k=effective_top_k,
            knowledge_base_id=kb_id,
            top_k_override=request.top_k,
            score_threshold_override=request.score_threshold,
        )

        payload_results = []
        for doc, score in results:
            matched_segments = await document_service.get_matched_segments(
                document=doc,
                query=request.query,
                tenant_id=tenant_id,
                user_id=user_id,
                max_segments=3,
            )
            payload_results.append(
                RetrievalTestResult(
                    document=DocumentResponse(**doc.to_dict()),
                    score=score,
                    matched_segments=[DocumentSegment(**segment) for segment in matched_segments],
                )
            )

        return RetrievalTestResponse(
            query=request.query,
            retrieval_method=settings.get("retrieval_method") or "vector",
            top_k=effective_top_k,
            score_threshold=effective_threshold,
            total=len(payload_results),
            results=payload_results,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to run retrieval test: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{kb_id}/evaluation-datasets", response_model=list[RetrievalTestSetResponse])
async def list_evaluation_datasets(
    kb_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
    eval_service: RetrievalEvaluationService = Depends(get_retrieval_eval_service),
):
    """列出知识库下的检索评测测试集"""
    try:
        items = await eval_service.list_test_sets(kb_id, tenant_id, user_id)
        return [RetrievalTestSetResponse(**item) for item in items]
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to list evaluation datasets: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{kb_id}/evaluation-datasets", response_model=RetrievalTestSetResponse, status_code=201)
async def create_evaluation_dataset(
    kb_id: str,
    request: RetrievalTestSetCreateRequest,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
    eval_service: RetrievalEvaluationService = Depends(get_retrieval_eval_service),
):
    """创建检索评测测试集"""
    try:
        dataset = await eval_service.create_test_set(
            kb_id=kb_id,
            tenant_id=tenant_id,
            user_id=user_id,
            name=request.name,
            description=request.description,
            cases=[case.dict() for case in request.cases],
        )
        return RetrievalTestSetResponse(**dataset)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create evaluation dataset: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{kb_id}/evaluation-datasets/{test_set_id}", response_model=RetrievalTestSetResponse)
async def update_evaluation_dataset(
    kb_id: str,
    test_set_id: str,
    request: RetrievalTestSetUpdateRequest,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
    eval_service: RetrievalEvaluationService = Depends(get_retrieval_eval_service),
):
    """更新检索评测测试集"""
    try:
        dataset = await eval_service.update_test_set(
            test_set_id=test_set_id,
            kb_id=kb_id,
            tenant_id=tenant_id,
            user_id=user_id,
            name=request.name,
            description=request.description,
            cases=[case.dict() for case in request.cases],
        )
        if not dataset:
            raise HTTPException(status_code=404, detail="Test set not found")
        return RetrievalTestSetResponse(**dataset)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update evaluation dataset: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{kb_id}/evaluation-datasets/{test_set_id}", status_code=204)
async def delete_evaluation_dataset(
    kb_id: str,
    test_set_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
    eval_service: RetrievalEvaluationService = Depends(get_retrieval_eval_service),
):
    """删除检索评测测试集"""
    try:
        deleted = await eval_service.delete_test_set(test_set_id, kb_id, tenant_id, user_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Test set not found")
        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete evaluation dataset: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{kb_id}/evaluation-runs", response_model=list[RetrievalEvaluationRunResponse])
async def list_evaluation_runs(
    kb_id: str,
    limit: int = Query(20, ge=1, le=100),
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
    eval_service: RetrievalEvaluationService = Depends(get_retrieval_eval_service),
):
    """列出检索评测运行"""
    try:
        items = await eval_service.list_runs(kb_id, tenant_id, user_id, limit)
        return [RetrievalEvaluationRunResponse(**item) for item in items]
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to list evaluation runs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{kb_id}/evaluation-runs", response_model=RetrievalEvaluationRunResponse, status_code=201)
async def run_evaluation(
    kb_id: str,
    request: RetrievalEvaluationRunRequest,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
    eval_service: RetrievalEvaluationService = Depends(get_retrieval_eval_service),
):
    """运行一组检索评测并保存结果"""
    try:
        run = await eval_service.run_evaluation(
            kb_id=kb_id,
            tenant_id=tenant_id,
            user_id=user_id,
            test_set_id=request.test_set_id,
            config_override=request.config.dict(exclude_none=True),
            name=request.name,
        )
        return RetrievalEvaluationRunResponse(**run)
    except ValueError as e:
        detail = str(e)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail)
    except Exception as e:
        logger.error(f"Failed to run evaluation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{kb_id}/evaluation-runs/{run_id}", response_model=RetrievalEvaluationRunResponse)
async def get_evaluation_run(
    kb_id: str,
    run_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
    eval_service: RetrievalEvaluationService = Depends(get_retrieval_eval_service),
):
    """获取单次检索评测详情"""
    try:
        run = await eval_service.get_run(run_id, kb_id, tenant_id, user_id)
        if not run:
            raise HTTPException(status_code=404, detail="Evaluation run not found")
        return RetrievalEvaluationRunResponse(**run)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get evaluation run: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{kb_id}/evaluation-runs/{run_id}/feedback", response_model=RetrievalEvaluationRunResponse)
async def update_evaluation_feedback(
    kb_id: str,
    run_id: str,
    request: RetrievalEvaluationFeedbackRequest,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
    eval_service: RetrievalEvaluationService = Depends(get_retrieval_eval_service),
):
    """更新单条样本人工评分"""
    try:
        run = await eval_service.update_run_feedback(
            run_id=run_id,
            kb_id=kb_id,
            tenant_id=tenant_id,
            user_id=user_id,
            case_id=request.case_id,
            manual_score=request.manual_score,
            manual_comment=request.manual_comment,
        )
        if not run:
            raise HTTPException(status_code=404, detail="Evaluation run not found")
        return RetrievalEvaluationRunResponse(**run)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update evaluation feedback: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{kb_id}/evaluation-runs/{run_id}/apply-config", response_model=RetrievalEvaluationApplyConfigResponse)
async def apply_evaluation_run_config(
    kb_id: str,
    run_id: str,
    tenant_id: str = Depends(get_current_tenant_id),
    user_id: Optional[str] = Depends(get_current_user_id),
    eval_service: RetrievalEvaluationService = Depends(get_retrieval_eval_service),
):
    """将某次评测配置设为生产检索配置"""
    try:
        settings = await eval_service.apply_run_config(run_id, kb_id, tenant_id, user_id)
        return RetrievalEvaluationApplyConfigResponse(
            retrieval_settings=RetrievalSettings(**settings),
            run_id=run_id,
        )
    except ValueError as e:
        detail = str(e)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail)
    except Exception as e:
        logger.error(f"Failed to apply evaluation config: {e}")
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
        docs, total = await document_service.list_documents(
            tenant_id=tenant_id,
            user_id=user_id,
            knowledge_base_id=kb_id,
            page=page,
            page_size=page_size,
        )

        return ListDocumentsResponse(
            documents=[DocumentResponse(**doc.to_dict()) for doc in docs],
            total=total,
            page=page,
            page_size=page_size,
        )

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
