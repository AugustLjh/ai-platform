"""
Knowledge Base Service
Business logic layer for knowledge base operations
"""
import logging
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime

from ..repositories.knowledge_base_repository import KnowledgeBaseRepository
from ..models.knowledge_base import (
    KnowledgeBase,
    AccessLevel,
    CreateKnowledgeBaseRequest,
    UpdateKnowledgeBaseRequest,
    KnowledgeBaseResponse,
    KnowledgeBaseWithStats,
    ListKnowledgeBasesResponse,
)

logger = logging.getLogger(__name__)


class KnowledgeBaseService:
    """知识库业务逻辑层"""

    def __init__(
        self,
        kb_repository: KnowledgeBaseRepository,
        audit_logger=None,
        quota_manager=None,
    ):
        self.kb_repository = kb_repository
        self.audit_logger = audit_logger
        self.quota_manager = quota_manager

    async def create_knowledge_base(
        self,
        tenant_id: str,
        request: CreateKnowledgeBaseRequest,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> KnowledgeBaseResponse:
        """
        创建知识库

        Args:
            tenant_id: 租户ID
            request: 创建请求
            user_id: 用户ID
            ip_address: IP地址
            user_agent: User Agent

        Returns:
            知识库响应对象
        """
        try:
            # Check quota if quota manager is available
            if self.quota_manager:
                try:
                    await self.quota_manager.check_knowledge_base_quota(tenant_id)
                except Exception as e:
                    logger.warning(f"Quota check failed: {e}")
                    # Continue anyway - quota is not critical

            # Determine user_id for private knowledge bases
            kb_user_id = user_id if request.access_level == AccessLevel.USER else None

            # Create knowledge base
            kb = await self.kb_repository.create_knowledge_base(
                tenant_id=tenant_id,
                name=request.name,
                description=request.description,
                user_id=kb_user_id,
                access_level=request.access_level,
                metadata=request.metadata,
            )

            # Audit log
            if self.audit_logger:
                try:
                    await self.audit_logger.log_knowledge_base_create(
                        user_id=user_id,
                        tenant_id=tenant_id,
                        resource_id=kb.id,
                        ip_address=ip_address,
                        user_agent=user_agent,
                        details={
                            "name": kb.name,
                            "access_level": kb.access_level.value,
                        }
                    )
                except Exception as e:
                    logger.error(f"Failed to log audit: {e}")

            return self._to_response(kb)

        except Exception as e:
            logger.error(f"Failed to create knowledge base: {e}")
            raise

    async def get_knowledge_base(
        self,
        kb_id: str,
        tenant_id: str,
        user_id: Optional[str] = None,
    ) -> Optional[KnowledgeBaseResponse]:
        """
        获取知识库

        Args:
            kb_id: 知识库ID
            tenant_id: 租户ID
            user_id: 用户ID

        Returns:
            知识库响应对象，如果不存在或无权限则返回None
        """
        kb = await self.kb_repository.get_knowledge_base(
            kb_id=kb_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        if kb:
            return self._to_response(kb)
        return None

    async def update_knowledge_base(
        self,
        kb_id: str,
        tenant_id: str,
        request: UpdateKnowledgeBaseRequest,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Optional[KnowledgeBaseResponse]:
        """
        更新知识库

        Args:
            kb_id: 知识库ID
            tenant_id: 租户ID
            request: 更新请求
            user_id: 用户ID
            ip_address: IP地址
            user_agent: User Agent

        Returns:
            更新后的知识库响应对象，如果不存在或无权限则返回None
        """
        try:
            kb = await self.kb_repository.update_knowledge_base(
                kb_id=kb_id,
                tenant_id=tenant_id,
                user_id=user_id,
                name=request.name,
                description=request.description,
                metadata=request.metadata,
            )

            if kb:
                # Audit log
                if self.audit_logger:
                    try:
                        await self.audit_logger.log_knowledge_base_update(
                            user_id=user_id,
                            tenant_id=tenant_id,
                            resource_id=kb.id,
                            ip_address=ip_address,
                            user_agent=user_agent,
                            details={
                                "name": kb.name,
                                "updated_fields": [k for k, v in request.dict(exclude_unset=True).items() if v is not None],
                            }
                        )
                    except Exception as e:
                        logger.error(f"Failed to log audit: {e}")

                return self._to_response(kb)

            return None

        except Exception as e:
            logger.error(f"Failed to update knowledge base: {e}")
            raise

    async def delete_knowledge_base(
        self,
        kb_id: str,
        tenant_id: str,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> bool:
        """
        删除知识库（级联删除所有文档）

        Args:
            kb_id: 知识库ID
            tenant_id: 租户ID
            user_id: 用户ID
            ip_address: IP地址
            user_agent: User Agent

        Returns:
            是否删除成功
        """
        try:
            # Get KB info before deletion for audit log
            kb = await self.kb_repository.get_knowledge_base(
                kb_id=kb_id,
                tenant_id=tenant_id,
                user_id=user_id,
            )

            if not kb:
                return False

            # Get document count for warning
            stats = await self.kb_repository.get_knowledge_base_stats(
                kb_id=kb_id,
                tenant_id=tenant_id,
                user_id=user_id,
            )
            doc_count = stats.get("document_count", 0) if stats else 0

            # Delete knowledge base (cascades to documents)
            success = await self.kb_repository.delete_knowledge_base(
                kb_id=kb_id,
                tenant_id=tenant_id,
                user_id=user_id,
            )

            if success:
                # Audit log
                if self.audit_logger:
                    try:
                        await self.audit_logger.log_knowledge_base_delete(
                            user_id=user_id,
                            tenant_id=tenant_id,
                            resource_id=kb_id,
                            ip_address=ip_address,
                            user_agent=user_agent,
                            details={
                                "name": kb.name,
                                "documents_deleted": doc_count,
                            }
                        )
                    except Exception as e:
                        logger.error(f"Failed to log audit: {e}")

                logger.info(f"Deleted knowledge base {kb_id} with {doc_count} documents")

            return success

        except Exception as e:
            logger.error(f"Failed to delete knowledge base: {e}")
            raise

    async def list_knowledge_bases(
        self,
        tenant_id: str,
        user_id: Optional[str] = None,
        access_level: Optional[AccessLevel] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> ListKnowledgeBasesResponse:
        """
        列出知识库（带统计信息）

        Args:
            tenant_id: 租户ID
            user_id: 用户ID
            access_level: 筛选访问级别
            page: 页码
            page_size: 每页数量

        Returns:
            知识库列表响应
        """
        kb_list, total = await self.kb_repository.list_knowledge_bases_with_stats(
            tenant_id=tenant_id,
            user_id=user_id,
            access_level=access_level,
            page=page,
            page_size=page_size,
        )

        knowledge_bases = [self._to_stats_response(kb) for kb in kb_list]

        return ListKnowledgeBasesResponse(
            knowledge_bases=knowledge_bases,
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get_knowledge_base_with_stats(
        self,
        kb_id: str,
        tenant_id: str,
        user_id: Optional[str] = None,
    ) -> Optional[KnowledgeBaseWithStats]:
        """
        获取知识库（带统计信息）

        Args:
            kb_id: 知识库ID
            tenant_id: 租户ID
            user_id: 用户ID

        Returns:
            带统计信息的知识库响应对象
        """
        stats = await self.kb_repository.get_knowledge_base_stats(
            kb_id=kb_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        if stats:
            return self._to_stats_response(stats)
        return None

    def _to_response(self, kb: KnowledgeBase) -> KnowledgeBaseResponse:
        """转换为响应对象"""
        return KnowledgeBaseResponse(
            id=kb.id,
            tenant_id=kb.tenant_id,
            user_id=kb.user_id,
            name=kb.name,
            description=kb.description,
            access_level=kb.access_level.value,
            created_at=kb.created_at.isoformat(),
            updated_at=kb.updated_at.isoformat(),
            metadata=kb.metadata,
        )

    def _to_stats_response(self, kb_dict: Dict[str, Any]) -> KnowledgeBaseWithStats:
        """转换为带统计信息的响应对象"""
        return KnowledgeBaseWithStats(
            id=kb_dict["id"],
            tenant_id=kb_dict["tenant_id"],
            user_id=kb_dict.get("user_id"),
            name=kb_dict["name"],
            description=kb_dict.get("description"),
            access_level=kb_dict["access_level"],
            created_at=kb_dict["created_at"] if isinstance(kb_dict["created_at"], str) else kb_dict["created_at"].isoformat(),
            updated_at=kb_dict["updated_at"] if isinstance(kb_dict["updated_at"], str) else kb_dict["updated_at"].isoformat(),
            metadata=kb_dict.get("metadata", {}),
            document_count=kb_dict.get("document_count", 0),
        )

    async def search_documents(
        self,
        tenant_id: str,
        user_id: Optional[str],
        query: str,
        top_k: int = 5,
        knowledge_base_id: Optional[str] = None,
    ) -> List[Tuple[Any, float]]:
        """Search documents for RAG retrieval"""
        from core.services.document_service import DocumentService
        from core.dependencies import get_container

        container = get_container()
        doc_service = container.get_document_service()

        return await doc_service.search_documents(
            tenant_id=tenant_id,
            user_id=user_id,
            query=query,
            top_k=top_k,
        )
