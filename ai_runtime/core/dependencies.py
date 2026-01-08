"""
Dependency Injection Container for AI Runtime
"""
import logging
from typing import Optional
from fastapi import Request, Header, HTTPException

from .config import AppConfig, get_config
from .database import DatabaseManager, get_db_manager
from .embeddings import SentenceTransformerEmbedding
from .repositories.knowledge_base import KnowledgeBaseRepository
from .services.knowledge_base import KnowledgeBaseService

logger = logging.getLogger(__name__)


class ServiceContainer:
    """Service container for dependency injection"""

    def __init__(self):
        self._embedding_service: Optional[SentenceTransformerEmbedding] = None
        self._kb_repository: Optional[KnowledgeBaseRepository] = None
        self._kb_service: Optional[KnowledgeBaseService] = None

    async def initialize(self, config: AppConfig, db_manager: DatabaseManager):
        """
        Initialize all services

        Args:
            config: Application configuration
            db_manager: Database manager
        """
        logger.info("🔧 Initializing services...")

        # Initialize embedding service
        logger.info(f"   Loading embedding model: {config.embedding.model_name}")
        self._embedding_service = SentenceTransformerEmbedding(
            model_name=config.embedding.model_name,
            device=config.embedding.device,
            cache_folder=config.embedding.cache_folder,
        )
        logger.info(f"   ✅ Embedding model loaded (dim={self._embedding_service.get_embedding_dimension()})")

        # Initialize repository
        self._kb_repository = KnowledgeBaseRepository(
            db_pool=db_manager.pool,
            use_pgvector=config.vector_search.use_pgvector,
        )
        logger.info(f"   ✅ Knowledge base repository initialized (pgvector={'enabled' if config.vector_search.use_pgvector else 'disabled'})")

        # Initialize audit logger
        from .audit import AuditLogger
        self._audit_logger = AuditLogger(
            db_pool=db_manager.pool,
            enabled=config.enable_audit_log,
        )
        logger.info(f"   ✅ Audit logger initialized ({'enabled' if config.enable_audit_log else 'disabled'})")

        # Initialize quota manager
        from .quota import QuotaManager
        self._quota_manager = QuotaManager(
            db_pool=db_manager.pool,
            config=config.quota,
        )
        logger.info("   ✅ Quota manager initialized")

        # Initialize service
        self._kb_service = KnowledgeBaseService(
            repository=self._kb_repository,
            embedding_service=self._embedding_service,
            audit_logger=self._audit_logger if config.enable_audit_log else None,
            quota_manager=self._quota_manager,
        )
        logger.info("   ✅ Knowledge base service initialized")

        logger.info("✅ All services initialized successfully")

    @property
    def embedding_service(self) -> SentenceTransformerEmbedding:
        """Get embedding service"""
        if self._embedding_service is None:
            raise RuntimeError("Embedding service not initialized")
        return self._embedding_service

    @property
    def kb_repository(self) -> KnowledgeBaseRepository:
        """Get knowledge base repository"""
        if self._kb_repository is None:
            raise RuntimeError("Knowledge base repository not initialized")
        return self._kb_repository

    @property
    def kb_service(self) -> KnowledgeBaseService:
        """Get knowledge base service"""
        if self._kb_service is None:
            raise RuntimeError("Knowledge base service not initialized")
        return self._kb_service


# Global service container
_container: Optional[ServiceContainer] = None


def get_container() -> ServiceContainer:
    """Get global service container"""
    global _container
    if _container is None:
        raise RuntimeError("Service container not initialized")
    return _container


def init_container() -> ServiceContainer:
    """Initialize global service container"""
    global _container
    if _container is None:
        _container = ServiceContainer()
    return _container


# ===== FastAPI Dependency Functions =====


async def get_kb_service() -> KnowledgeBaseService:
    """
    FastAPI dependency: Get knowledge base service

    Returns:
        KnowledgeBaseService instance
    """
    return get_container().kb_service


async def get_current_tenant_id(
    request: Request,
    x_tenant_id: Optional[str] = Header(None),
) -> str:
    """
    FastAPI dependency: Get current tenant ID

    Extracts tenant ID from:
    1. X-Tenant-ID header
    2. Request state (from JWT middleware)
    3. Query parameter (for testing)

    Args:
        request: FastAPI request
        x_tenant_id: Tenant ID from header

    Returns:
        Tenant ID

    Raises:
        HTTPException: If tenant ID not found
    """
    # 1. Check header
    if x_tenant_id:
        return x_tenant_id

    # 2. Check request state (set by JWT middleware)
    tenant_id = getattr(request.state, "tenant_id", None)
    if tenant_id:
        return tenant_id

    # 3. Check query parameter (for testing only)
    tenant_id = request.query_params.get("tenant_id")
    if tenant_id:
        logger.warning("Using tenant_id from query parameter (testing mode)")
        return tenant_id

    # 4. Default for development
    logger.warning("No tenant ID found, using default 'default-tenant' (development mode)")
    return "default-tenant"


async def get_current_user_id(
    request: Request,
    x_user_id: Optional[str] = Header(None),
) -> Optional[str]:
    """
    FastAPI dependency: Get current user ID

    Extracts user ID from:
    1. X-User-ID header
    2. Request state (from JWT middleware)
    3. Query parameter (for testing)

    Args:
        request: FastAPI request
        x_user_id: User ID from header

    Returns:
        User ID or None
    """
    # 1. Check header
    if x_user_id:
        return x_user_id

    # 2. Check request state (set by JWT middleware)
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return user_id

    # 3. Check query parameter (for testing only)
    user_id = request.query_params.get("user_id")
    if user_id:
        logger.warning("Using user_id from query parameter (testing mode)")
        return user_id

    return None


async def get_current_request_context(
    request: Request,
) -> dict:
    """
    FastAPI dependency: Get request context for audit logging

    Returns:
        Dictionary with request metadata
    """
    return {
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
        "path": request.url.path,
        "method": request.method,
    }
