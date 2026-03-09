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

DEFAULT_INDEXING_SETTINGS = {
    "indexing_method": "chunk",
    "chunk_size": 500,
    "chunk_overlap": 50,
    "embedding_model_id": None,
}

DEFAULT_RETRIEVAL_SETTINGS = {
    "retrieval_method": "vector",
    "top_k": 5,
    "score_threshold": 0.0,
    "enable_rerank": False,
    "rerank_model_id": None,
}

DEFAULT_GOVERNANCE_SETTINGS = {
    "config_version": 1,
    "budget_alert_usd": None,
    "low_quality_threshold": 2.0,
    "routes": {
        "chat": {
            "enabled": True,
            "primary_model_id": None,
            "fallback_model_id": None,
        },
        "rag_chat": {
            "enabled": True,
            "primary_model_id": None,
            "fallback_model_id": None,
        },
        "agent_chat": {
            "enabled": True,
            "primary_model_id": None,
            "fallback_model_id": None,
        },
    },
}


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

    async def get_indexing_settings(
        self,
        kb_id: str,
        tenant_id: str,
        user_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        kb = await self.kb_repository.get_knowledge_base(
            kb_id=kb_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        if not kb:
            return None

        return self._normalize_settings(kb.metadata, "indexing_settings", DEFAULT_INDEXING_SETTINGS)

    async def update_indexing_settings(
        self,
        kb_id: str,
        tenant_id: str,
        updates: Dict[str, Any],
        user_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        kb = await self.kb_repository.get_knowledge_base(
            kb_id=kb_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        if not kb:
            return None

        metadata = dict(kb.metadata or {})
        current_settings = metadata.get("indexing_settings")
        if not isinstance(current_settings, dict):
            current_settings = {}

        for key, value in updates.items():
            if value == "":
                value = None
            current_settings[key] = value

        metadata["indexing_settings"] = current_settings

        updated_kb = await self.kb_repository.update_knowledge_base(
            kb_id=kb_id,
            tenant_id=tenant_id,
            user_id=user_id,
            metadata=metadata,
        )

        if not updated_kb:
            return None

        return self._normalize_settings(updated_kb.metadata, "indexing_settings", DEFAULT_INDEXING_SETTINGS)

    async def get_retrieval_settings(
        self,
        kb_id: str,
        tenant_id: str,
        user_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        kb = await self.kb_repository.get_knowledge_base(
            kb_id=kb_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        if not kb:
            return None

        return self._normalize_settings(kb.metadata, "retrieval_settings", DEFAULT_RETRIEVAL_SETTINGS)

    async def update_retrieval_settings(
        self,
        kb_id: str,
        tenant_id: str,
        updates: Dict[str, Any],
        user_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        kb = await self.kb_repository.get_knowledge_base(
            kb_id=kb_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        if not kb:
            return None

        metadata = dict(kb.metadata or {})
        current_settings = metadata.get("retrieval_settings")
        if not isinstance(current_settings, dict):
            current_settings = {}

        for key, value in updates.items():
            if value == "":
                value = None
            current_settings[key] = value

        metadata["retrieval_settings"] = current_settings

        updated_kb = await self.kb_repository.update_knowledge_base(
            kb_id=kb_id,
            tenant_id=tenant_id,
            user_id=user_id,
            metadata=metadata,
        )

        if not updated_kb:
            return None

        return self._normalize_settings(updated_kb.metadata, "retrieval_settings", DEFAULT_RETRIEVAL_SETTINGS)

    async def get_governance_settings(
        self,
        kb_id: str,
        tenant_id: str,
        user_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        kb = await self.kb_repository.get_knowledge_base(
            kb_id=kb_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        if not kb:
            return None

        return self._normalize_governance_settings(kb.metadata)

    async def update_governance_settings(
        self,
        kb_id: str,
        tenant_id: str,
        updates: Dict[str, Any],
        user_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        kb = await self.kb_repository.get_knowledge_base(
            kb_id=kb_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        if not kb:
            return None

        current_settings = self._normalize_governance_settings(kb.metadata)
        next_settings = {
            "config_version": current_settings.get("config_version", 1),
            "budget_alert_usd": current_settings.get("budget_alert_usd"),
            "low_quality_threshold": current_settings.get("low_quality_threshold", 2.0),
            "routes": {
                scene: dict(route or {})
                for scene, route in (current_settings.get("routes") or {}).items()
            },
        }

        if "budget_alert_usd" in updates:
            next_settings["budget_alert_usd"] = updates.get("budget_alert_usd")

        if updates.get("low_quality_threshold") is not None:
            next_settings["low_quality_threshold"] = updates["low_quality_threshold"]

        if isinstance(updates.get("routes"), dict):
            for scene, route_updates in updates["routes"].items():
                if not isinstance(route_updates, dict):
                    continue
                current_route = next_settings["routes"].get(scene)
                if not isinstance(current_route, dict):
                    current_route = {
                        "enabled": True,
                        "primary_model_id": None,
                        "fallback_model_id": None,
                    }
                for key, value in route_updates.items():
                    if value == "":
                        value = None
                    current_route[key] = value
                if current_route.get("primary_model_id") == current_route.get("fallback_model_id"):
                    current_route["fallback_model_id"] = None
                next_settings["routes"][scene] = current_route

        if next_settings != current_settings:
            next_settings["config_version"] = int(current_settings.get("config_version", 1)) + 1

        metadata = dict(kb.metadata or {})
        metadata["ai_governance_settings"] = next_settings

        updated_kb = await self.kb_repository.update_knowledge_base(
            kb_id=kb_id,
            tenant_id=tenant_id,
            user_id=user_id,
            metadata=metadata,
        )

        if not updated_kb:
            return None

        return self._normalize_governance_settings(updated_kb.metadata)

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

    def _normalize_settings(
        self,
        metadata: Optional[Dict[str, Any]],
        key: str,
        defaults: Dict[str, Any],
    ) -> Dict[str, Any]:
        settings = {}
        if isinstance(metadata, dict):
            settings = metadata.get(key) if isinstance(metadata.get(key), dict) else {}
        merged = dict(defaults)
        merged.update(settings or {})
        return merged

    def _normalize_governance_settings(
        self,
        metadata: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        settings = self._normalize_settings(
            metadata=metadata,
            key="ai_governance_settings",
            defaults=DEFAULT_GOVERNANCE_SETTINGS,
        )
        default_routes = DEFAULT_GOVERNANCE_SETTINGS["routes"]
        current_routes = settings.get("routes") if isinstance(settings.get("routes"), dict) else {}
        normalized_routes: Dict[str, Dict[str, Any]] = {}
        for scene, defaults in default_routes.items():
            route = current_routes.get(scene) if isinstance(current_routes.get(scene), dict) else {}
            merged_route = dict(defaults)
            merged_route.update(route or {})
            if merged_route.get("primary_model_id") == "":
                merged_route["primary_model_id"] = None
            if merged_route.get("fallback_model_id") == "":
                merged_route["fallback_model_id"] = None
            if merged_route.get("primary_model_id") == merged_route.get("fallback_model_id"):
                merged_route["fallback_model_id"] = None
            normalized_routes[scene] = merged_route

        settings["routes"] = normalized_routes
        settings["config_version"] = int(settings.get("config_version") or 1)
        settings["low_quality_threshold"] = float(settings.get("low_quality_threshold") or 2.0)
        if settings.get("budget_alert_usd") == "":
            settings["budget_alert_usd"] = None
        return settings

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
        doc_service = container.document_service

        return await doc_service.search_documents(
            tenant_id=tenant_id,
            user_id=user_id,
            query=query,
            top_k=top_k,
            knowledge_base_id=knowledge_base_id,
        )
