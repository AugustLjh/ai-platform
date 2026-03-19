"""
Dependency Injection Container for AI Runtime
"""
import logging
from typing import Optional
from fastapi import Request, Header, HTTPException

from .config import AppConfig, get_config
from .database import DatabaseManager, get_db_manager
from .embeddings import EmbeddingService, SentenceTransformerEmbedding, OpenAIEmbedding, JinaEmbedding
from .repositories.document_repository import DocumentRepository
from .repositories.knowledge_base_repository import KnowledgeBaseRepository
from .repositories.retrieval_evaluation_repository import RetrievalEvaluationRepository
from .services.document_service import DocumentService
from .services.knowledge_base_service import KnowledgeBaseService
from .services.retrieval_evaluation_service import RetrievalEvaluationService
from .vector_index import QdrantVectorIndex, VectorIndex

logger = logging.getLogger(__name__)


class ServiceContainer:
    """Service container for dependency injection"""

    def __init__(self):
        self._embedding_service: Optional[EmbeddingService] = None
        self._kb_repository: Optional[KnowledgeBaseRepository] = None
        self._document_repository: Optional[DocumentRepository] = None
        self._retrieval_eval_repository: Optional[RetrievalEvaluationRepository] = None
        self._kb_service: Optional[KnowledgeBaseService] = None
        self._document_service: Optional[DocumentService] = None
        self._retrieval_eval_service: Optional[RetrievalEvaluationService] = None
        self._vector_index: Optional[VectorIndex] = None

    async def initialize(self, config: AppConfig, db_manager: DatabaseManager):
        """
        Initialize all services

        Args:
            config: Application configuration
            db_manager: Database manager
        """
        logger.info("🔧 Initializing services...")

        # Initialize embedding service based on provider
        provider = config.embedding.provider.lower()
        logger.info(f"   Loading embedding service: {provider} / {config.embedding.model_name}")

        if provider == "openai":
            if not config.embedding.api_key:
                raise ValueError("EMBEDDING_API_KEY is required for OpenAI provider")
            self._embedding_service = OpenAIEmbedding(
                api_key=config.embedding.api_key,
                model_name=config.embedding.model_name,
                api_base=config.embedding.api_base,
            )
        elif provider == "jina":
            if not config.embedding.api_key:
                raise ValueError("EMBEDDING_API_KEY is required for Jina provider")
            self._embedding_service = JinaEmbedding(
                api_key=config.embedding.api_key,
                model_name=config.embedding.model_name,
                api_base=config.embedding.api_base,
            )
        elif provider == "local":
            self._embedding_service = SentenceTransformerEmbedding(
                model_name=config.embedding.model_name,
                device=config.embedding.device,
                cache_folder=config.embedding.cache_folder,
            )
        else:
            raise ValueError(f"Unknown embedding provider: {provider}")

        logger.info(f"   ✅ Embedding service loaded (dim={self._embedding_service.get_embedding_dimension()})")

        # Initialize repositories
        self._kb_repository = KnowledgeBaseRepository(
            db_pool=db_manager.pool,
        )
        logger.info("   ✅ Knowledge base repository initialized")

        self._document_repository = DocumentRepository(
            db_pool=db_manager.pool,
        )
        logger.info("   ✅ Document repository initialized (PostgreSQL metadata + keyword search)")

        self._vector_index = QdrantVectorIndex(
            config=config.qdrant,
        )
        await self._vector_index.initialize()
        logger.info("   ✅ Vector index initialized (qdrant)")

        self._retrieval_eval_repository = RetrievalEvaluationRepository(
            db_pool=db_manager.pool,
        )
        logger.info("   ✅ Retrieval evaluation repository initialized")

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

        # Initialize services
        self._kb_service = KnowledgeBaseService(
            kb_repository=self._kb_repository,
            audit_logger=self._audit_logger if config.enable_audit_log else None,
            quota_manager=self._quota_manager,
        )
        logger.info("   ✅ Knowledge base service initialized")

        self._document_service = DocumentService(
            repository=self._document_repository,
            kb_repository=self._kb_repository,
            embedding_service=self._embedding_service,
            vector_index=self._vector_index,
            audit_logger=self._audit_logger if config.enable_audit_log else None,
            quota_manager=self._quota_manager,
        )
        await self._document_service.start_index_worker()
        logger.info("   ✅ Document service initialized")

        self._retrieval_eval_service = RetrievalEvaluationService(
            repository=self._retrieval_eval_repository,
            kb_service=self._kb_service,
            document_service=self._document_service,
        )
        logger.info("   ✅ Retrieval evaluation service initialized")

        logger.info("✅ All services initialized successfully")

    @property
    def embedding_service(self) -> EmbeddingService:
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
    def document_repository(self) -> DocumentRepository:
        """Get document repository"""
        if self._document_repository is None:
            raise RuntimeError("Document repository not initialized")
        return self._document_repository

    @property
    def kb_service(self) -> KnowledgeBaseService:
        """Get knowledge base service"""
        if self._kb_service is None:
            raise RuntimeError("Knowledge base service not initialized")
        return self._kb_service

    @property
    def document_service(self) -> DocumentService:
        """Get document service"""
        if self._document_service is None:
            raise RuntimeError("Document service not initialized")
        return self._document_service

    @property
    def retrieval_eval_service(self) -> RetrievalEvaluationService:
        """Get retrieval evaluation service"""
        if self._retrieval_eval_service is None:
            raise RuntimeError("Retrieval evaluation service not initialized")
        return self._retrieval_eval_service

    @property
    def vector_index(self) -> VectorIndex:
        """Get vector index backend"""
        if self._vector_index is None:
            raise RuntimeError("Vector index not initialized")
        return self._vector_index

    async def shutdown(self):
        """Close backend resources"""
        if self._document_service is not None:
            await self._document_service.stop_index_worker()
        if self._vector_index is not None:
            await self._vector_index.close()


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


async def get_document_service() -> DocumentService:
    """
    FastAPI dependency: Get document service

    Returns:
        DocumentService instance
    """
    return get_container().document_service


async def get_retrieval_eval_service() -> RetrievalEvaluationService:
    """
    FastAPI dependency: Get retrieval evaluation service

    Returns:
        RetrievalEvaluationService instance
    """
    return get_container().retrieval_eval_service


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
