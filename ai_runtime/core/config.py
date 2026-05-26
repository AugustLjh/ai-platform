"""
Configuration Management for AI Runtime
"""
import os
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class DatabaseConfig(BaseModel):
    """Database configuration"""
    host: str = Field(default="localhost", description="Database host")
    port: int = Field(default=5432, description="Database port")
    user: str = Field(default="ai_user", description="Database user")
    password: str = Field(default="", description="Database password")
    database: str = Field(default="ai_platform", description="Database name")
    min_pool_size: int = Field(default=5, description="Minimum pool size")
    max_pool_size: int = Field(default=20, description="Maximum pool size")
    sslmode: str = Field(default="disable", description="SSL mode")

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        """Load from environment variables"""
        return cls(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            user=os.getenv("POSTGRES_USER", "ai_user"),
            password=os.getenv("POSTGRES_PASSWORD", ""),
            database=os.getenv("POSTGRES_DB", os.getenv("POSTGRES_NAME", "ai_platform")),
            min_pool_size=int(os.getenv("POSTGRES_MIN_CONNS", os.getenv("POSTGRES_MIN_POOL_SIZE", "5"))),
            max_pool_size=int(os.getenv("POSTGRES_MAX_CONNS", os.getenv("POSTGRES_MAX_POOL_SIZE", "20"))),
            sslmode=os.getenv("POSTGRES_SSLMODE", "disable"),
        )


class EmbeddingConfig(BaseModel):
    """Embedding model configuration"""
    model_config = ConfigDict(protected_namespaces=())

    provider: str = Field(
        default="local",
        description="Embedding provider: local/openai/jina"
    )
    model_name: str = Field(
        default="paraphrase-multilingual-MiniLM-L12-v2",
        description="Model name"
    )
    api_key: Optional[str] = Field(default=None, description="API key for online services")
    api_base: Optional[str] = Field(default=None, description="API base URL")
    device: Optional[str] = Field(default=None, description="Device (cpu/cuda) for local models")
    cache_folder: Optional[str] = Field(default=None, description="Model cache folder for local models")

    @classmethod
    def from_env(cls) -> "EmbeddingConfig":
        """Load from environment variables"""
        return cls(
            provider=os.getenv("EMBEDDING_PROVIDER", "local"),
            model_name=os.getenv(
                "EMBEDDING_MODEL",
                "paraphrase-multilingual-MiniLM-L12-v2"
            ),
            api_key=os.getenv("EMBEDDING_API_KEY"),
            api_base=os.getenv("EMBEDDING_API_BASE"),
            device=os.getenv("EMBEDDING_DEVICE"),
            cache_folder=os.getenv("EMBEDDING_CACHE_FOLDER"),
        )


class LLMConfig(BaseModel):
    """LLM configuration"""
    provider: str = Field(
        default="mock",
        description="LLM provider: openai/deepseek/jina/qwen/wenxin/glm/kimi/doubao/local/mock",
    )
    api_key: Optional[str] = Field(default=None, description="API key for LLM service")
    api_base: Optional[str] = Field(default=None, description="API base URL")
    model: str = Field(default="gpt-3.5-turbo", description="Model name")
    timeout: int = Field(default=30, description="Request timeout in seconds")
    max_retries: int = Field(default=3, description="Maximum retries")

    @classmethod
    def from_env(cls) -> "LLMConfig":
        """Load from environment variables"""
        provider = os.getenv("LLM_PROVIDER", "mock").lower()
        provider_defaults = {
            "openai": ("OPENAI_API_KEY", "OPENAI_API_BASE", "OPENAI_MODEL", "gpt-3.5-turbo"),
            "deepseek": ("DEEPSEEK_API_KEY", "DEEPSEEK_API_BASE", "DEEPSEEK_MODEL", "deepseek-chat"),
            "jina": ("JINA_API_KEY", "JINA_API_BASE", "JINA_MODEL", "jina-deepsearch-v1"),
            "qwen": ("QWEN_API_KEY", "QWEN_API_BASE", "QWEN_MODEL", "qwen-plus"),
            "wenxin": ("WENXIN_API_KEY", "WENXIN_API_BASE", "WENXIN_MODEL", "ernie-4.0-turbo-8k"),
            "glm": ("GLM_API_KEY", "GLM_API_BASE", "GLM_MODEL", "glm-4-plus"),
            "kimi": ("KIMI_API_KEY", "KIMI_API_BASE", "KIMI_MODEL", "moonshot-v1-8k"),
            "doubao": ("DOUBAO_API_KEY", "DOUBAO_API_BASE", "DOUBAO_MODEL", "doubao-seed-1-6"),
            "local": ("", "", "LOCAL_MODEL", "local-model"),
            "mock": ("", "", "MOCK_MODEL", "gpt-3.5-turbo"),
        }
        api_key_env, api_base_env, model_env, default_model = provider_defaults.get(
            provider,
            ("OPENAI_API_KEY", "OPENAI_API_BASE", "OPENAI_MODEL", "gpt-3.5-turbo"),
        )
        return cls(
            provider=provider,
            api_key=os.getenv(api_key_env) if api_key_env else None,
            api_base=os.getenv(api_base_env) if api_base_env else None,
            model=os.getenv(model_env, default_model) if model_env else default_model,
            timeout=int(os.getenv("LLM_TIMEOUT", "30")),
            max_retries=int(os.getenv("LLM_MAX_RETRIES", "3")),
        )


class QuotaConfig(BaseModel):
    """Quota configuration"""
    max_documents_per_tenant: int = Field(
        default=10000,
        description="Maximum documents per tenant"
    )
    max_document_size: int = Field(
        default=10 * 1024 * 1024,  # 10MB
        description="Maximum document size in bytes"
    )
    max_upload_file_size: int = Field(
        default=20 * 1024 * 1024,  # 20MB
        description="Maximum upload file size"
    )

    @classmethod
    def from_env(cls) -> "QuotaConfig":
        """Load from environment variables"""
        return cls(
            max_documents_per_tenant=int(os.getenv("MAX_DOCUMENTS_PER_TENANT", "10000")),
            max_document_size=int(os.getenv("MAX_DOCUMENT_SIZE", str(10 * 1024 * 1024))),
            max_upload_file_size=int(os.getenv("MAX_UPLOAD_FILE_SIZE", str(20 * 1024 * 1024))),
        )


class VectorSearchConfig(BaseModel):
    """Vector search configuration"""
    top_k: int = Field(default=5, description="Maximum results for vector search")
    similarity_threshold: float = Field(default=0.7, description="Vector similarity threshold (0-1)")

    @classmethod
    def from_env(cls) -> "VectorSearchConfig":
        """Load from environment variables"""
        return cls(
            top_k=int(os.getenv("VECTOR_SEARCH_TOP_K", "5")),
            similarity_threshold=float(os.getenv("VECTOR_SIMILARITY_THRESHOLD", "0.7")),
        )


class QdrantConfig(BaseModel):
    """Qdrant configuration"""
    url: Optional[str] = Field(default=None, description="Full Qdrant URL, e.g. http://qdrant:6333")
    host: str = Field(default="localhost", description="Qdrant host")
    port: int = Field(default=6333, description="Qdrant HTTP port")
    grpc_port: int = Field(default=6334, description="Qdrant gRPC port")
    api_key: Optional[str] = Field(default=None, description="Qdrant API key")
    prefer_grpc: bool = Field(default=False, description="Prefer gRPC client transport")
    use_https: bool = Field(default=False, description="Use HTTPS when URL is not explicitly set")
    timeout: float = Field(default=10.0, description="Qdrant request timeout in seconds")
    collection_prefix: str = Field(default="document_chunks", description="Collection prefix for chunk vectors")

    @classmethod
    def from_env(cls) -> "QdrantConfig":
        """Load from environment variables"""
        return cls(
            url=os.getenv("QDRANT_URL"),
            host=os.getenv("QDRANT_HOST", "localhost"),
            port=int(os.getenv("QDRANT_PORT", "6333")),
            grpc_port=int(os.getenv("QDRANT_GRPC_PORT", "6334")),
            api_key=os.getenv("QDRANT_API_KEY"),
            prefer_grpc=os.getenv("QDRANT_PREFER_GRPC", "false").lower() == "true",
            use_https=os.getenv("QDRANT_USE_HTTPS", "false").lower() == "true",
            timeout=float(os.getenv("QDRANT_TIMEOUT", "10")),
            collection_prefix=os.getenv("QDRANT_COLLECTION_PREFIX", "document_chunks"),
        )


class RAGConfig(BaseModel):
    """RAG configuration"""
    top_k: int = Field(default=5, description="Number of documents to retrieve")
    max_context_length: int = Field(default=2000, description="Maximum context length in tokens")
    enable_reranking: bool = Field(default=False, description="Enable RAG reranking")

    @classmethod
    def from_env(cls) -> "RAGConfig":
        """Load from environment variables"""
        return cls(
            top_k=int(os.getenv("RAG_TOP_K", "5")),
            max_context_length=int(os.getenv("RAG_MAX_CONTEXT_LENGTH", "2000")),
            enable_reranking=os.getenv("RAG_ENABLE_RERANKING", "false").lower() == "true",
        )


class AgentConfig(BaseModel):
    """Agent configuration"""
    max_iterations: int = Field(default=10, description="Maximum iterations for agent")
    timeout: int = Field(default=60, description="Agent timeout in seconds")
    log_tool_calls: bool = Field(default=True, description="Enable tool call logging")

    @classmethod
    def from_env(cls) -> "AgentConfig":
        """Load from environment variables"""
        return cls(
            max_iterations=int(os.getenv("AGENT_MAX_ITERATIONS", "10")),
            timeout=int(os.getenv("AGENT_TIMEOUT", "60")),
            log_tool_calls=os.getenv("AGENT_LOG_TOOL_CALLS", "true").lower() == "true",
        )


class ServerConfig(BaseModel):
    """Server configuration"""
    host: str = Field(default="0.0.0.0", description="Server host")
    http_port: int = Field(default=8000, description="HTTP port")
    grpc_port: int = Field(default=50051, description="gRPC port")

    @classmethod
    def from_env(cls) -> "ServerConfig":
        """Load from environment variables"""
        return cls(
            host=os.getenv("SERVER_HOST", "0.0.0.0"),
            http_port=int(os.getenv("HTTP_PORT", "8000")),
            grpc_port=int(os.getenv("GRPC_PORT", "50051")),
        )


class SecurityConfig(BaseModel):
    """Security configuration"""
    enable_api_key_auth: bool = Field(default=False, description="Enable API key authentication")
    api_key: Optional[str] = Field(default=None, description="API key")
    enable_cors: bool = Field(default=True, description="Enable CORS")
    cors_allowed_origins: str = Field(default="*", description="Allowed origins")

    @classmethod
    def from_env(cls) -> "SecurityConfig":
        """Load from environment variables"""
        return cls(
            enable_api_key_auth=os.getenv("ENABLE_API_KEY_AUTH", "false").lower() == "true",
            api_key=os.getenv("API_KEY"),
            enable_cors=os.getenv("ENABLE_CORS", "true").lower() == "true",
            cors_allowed_origins=os.getenv("CORS_ALLOWED_ORIGINS", "*"),
        )


class LoggingConfig(BaseModel):
    """Logging configuration"""
    level: str = Field(default="INFO", description="Log level")
    format: str = Field(default="text", description="Log format (json/text)")
    to_file: bool = Field(default=False, description="Output to file")
    file_path: Optional[str] = Field(default=None, description="Log file path")

    @classmethod
    def from_env(cls) -> "LoggingConfig":
        """Load from environment variables"""
        return cls(
            level=os.getenv("LOG_LEVEL", "INFO"),
            format=os.getenv("LOG_FORMAT", "text"),
            to_file=os.getenv("LOG_TO_FILE", "false").lower() == "true",
            file_path=os.getenv("LOG_FILE_PATH"),
        )


class PerformanceConfig(BaseModel):
    """Performance configuration"""
    workers: int = Field(default=0, description="Number of workers (0 for auto-detect)")
    threads_per_worker: int = Field(default=1, description="Threads per worker")
    request_queue_size: int = Field(default=100, description="Request queue size")

    @classmethod
    def from_env(cls) -> "PerformanceConfig":
        """Load from environment variables"""
        return cls(
            workers=int(os.getenv("WORKERS", "0")),
            threads_per_worker=int(os.getenv("THREADS_PER_WORKER", "1")),
            request_queue_size=int(os.getenv("REQUEST_QUEUE_SIZE", "100")),
        )


class MonitoringConfig(BaseModel):
    """Monitoring configuration"""
    metrics_port: Optional[int] = Field(default=None, description="Prometheus metrics port")
    enable_health_check: bool = Field(default=True, description="Enable health check endpoint")
    health_check_path: str = Field(default="/health", description="Health check path")

    @classmethod
    def from_env(cls) -> "MonitoringConfig":
        """Load from environment variables"""
        metrics_port_str = os.getenv("METRICS_PORT")
        return cls(
            metrics_port=int(metrics_port_str) if metrics_port_str else None,
            enable_health_check=os.getenv("ENABLE_HEALTH_CHECK", "true").lower() == "true",
            health_check_path=os.getenv("HEALTH_CHECK_PATH", "/health"),
        )


class AppConfig(BaseModel):
    """Application configuration"""
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    quota: QuotaConfig = Field(default_factory=QuotaConfig)
    vector_search: VectorSearchConfig = Field(default_factory=VectorSearchConfig)
    qdrant: QdrantConfig = Field(default_factory=QdrantConfig)
    rag: RAGConfig = Field(default_factory=RAGConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    performance: PerformanceConfig = Field(default_factory=PerformanceConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)

    # Feature flags
    enable_audit_log: bool = Field(default=True, description="Enable audit logging")
    enable_performance_monitoring: bool = Field(default=False, description="Enable performance monitoring")
    enable_debug: bool = Field(default=False, description="Enable debug mode")
    environment: str = Field(default="development", description="Environment (development/staging/production)")

    @classmethod
    def from_env(cls) -> "AppConfig":
        """Load all configuration from environment variables"""
        return cls(
            database=DatabaseConfig.from_env(),
            embedding=EmbeddingConfig.from_env(),
            llm=LLMConfig.from_env(),
            quota=QuotaConfig.from_env(),
            vector_search=VectorSearchConfig.from_env(),
            qdrant=QdrantConfig.from_env(),
            rag=RAGConfig.from_env(),
            agent=AgentConfig.from_env(),
            server=ServerConfig.from_env(),
            security=SecurityConfig.from_env(),
            logging=LoggingConfig.from_env(),
            performance=PerformanceConfig.from_env(),
            monitoring=MonitoringConfig.from_env(),
            enable_audit_log=os.getenv("ENABLE_AUDIT_LOG", "true").lower() == "true",
            enable_performance_monitoring=os.getenv("ENABLE_PERFORMANCE_MONITORING", "false").lower() == "true",
            enable_debug=os.getenv("ENABLE_DEBUG", "false").lower() == "true",
            environment=os.getenv("ENVIRONMENT", "development"),
        )

    def print_summary(self):
        """Print configuration summary"""
        print("=" * 70)
        print("AI Runtime Configuration")
        print("=" * 70)
        print(f"Environment: {self.environment}")
        print(f"Debug Mode: {'Enabled' if self.enable_debug else 'Disabled'}")
        print()
        print("Database:")
        print(f"  Host: {self.database.host}:{self.database.port}")
        print(f"  Database: {self.database.database}")
        print(f"  Pool Size: {self.database.min_pool_size}-{self.database.max_pool_size}")
        print(f"  SSL Mode: {self.database.sslmode}")
        print()
        print("Embedding:")
        print(f"  Provider: {self.embedding.provider}")
        print(f"  Model: {self.embedding.model_name}")
        if self.embedding.device:
            print(f"  Device: {self.embedding.device}")
        print()
        print("LLM:")
        print(f"  Provider: {self.llm.provider}")
        print(f"  Model: {self.llm.model}")
        print(f"  Timeout: {self.llm.timeout}s")
        print()
        print("Vector Search:")
        print(f"  Top K: {self.vector_search.top_k}")
        print(f"  Similarity Threshold: {self.vector_search.similarity_threshold}")
        endpoint = self.qdrant.url or f"http{'s' if self.qdrant.use_https else ''}://{self.qdrant.host}:{self.qdrant.port}"
        print(f"  Qdrant Endpoint: {endpoint}")
        print(f"  Collection Prefix: {self.qdrant.collection_prefix}")
        print()
        print("RAG:")
        print(f"  Top K: {self.rag.top_k}")
        print(f"  Max Context Length: {self.rag.max_context_length}")
        print(f"  Enable Reranking: {self.rag.enable_reranking}")
        print()
        print("Agent:")
        print(f"  Max Iterations: {self.agent.max_iterations}")
        print(f"  Timeout: {self.agent.timeout}s")
        print(f"  Log Tool Calls: {self.agent.log_tool_calls}")
        print()
        print("Quota:")
        print(f"  Max Documents/Tenant: {self.quota.max_documents_per_tenant}")
        print(f"  Max Document Size: {self.quota.max_document_size / 1024 / 1024:.1f}MB")
        print(f"  Max Upload Size: {self.quota.max_upload_file_size / 1024 / 1024:.1f}MB")
        print()
        print("Server:")
        print(f"  Host: {self.server.host}")
        print(f"  HTTP Port: {self.server.http_port}")
        print(f"  gRPC Port: {self.server.grpc_port}")
        print()
        print("Security:")
        print(f"  API Key Auth: {'Enabled' if self.security.enable_api_key_auth else 'Disabled'}")
        print(f"  CORS: {'Enabled' if self.security.enable_cors else 'Disabled'}")
        if self.security.enable_cors:
            print(f"  CORS Origins: {self.security.cors_allowed_origins}")
        print()
        print("Features:")
        print(f"  Audit Log: {'Enabled' if self.enable_audit_log else 'Disabled'}")
        print(f"  Performance Monitoring: {'Enabled' if self.enable_performance_monitoring else 'Disabled'}")
        print()
        print("Logging:")
        print(f"  Level: {self.logging.level}")
        print(f"  Format: {self.logging.format}")
        print(f"  To File: {self.logging.to_file}")
        if self.logging.to_file and self.logging.file_path:
            print(f"  File Path: {self.logging.file_path}")
        print("=" * 70)


# Global configuration instance
_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """Get global configuration instance"""
    global _config
    if _config is None:
        _config = AppConfig.from_env()
    return _config


def load_env_file(env_file: str = ".env"):
    """Load environment variables from .env file"""
    try:
        from dotenv import load_dotenv
        load_dotenv(env_file)
        print(f"[OK] Loaded environment from {env_file}")
    except ImportError:
        print("[WARN] python-dotenv not installed, using system environment variables")
    except FileNotFoundError:
        print(f"[WARN] {env_file} not found, using default configuration")
