"""
Configuration Management for AI Runtime
"""
import os
from typing import Optional
from pydantic import BaseModel, Field


class DatabaseConfig(BaseModel):
    """Database configuration"""
    host: str = Field(default="localhost", description="Database host")
    port: int = Field(default=5432, description="Database port")
    user: str = Field(default="ai_user", description="Database user")
    password: str = Field(default="", description="Database password")
    database: str = Field(default="ai_platform", description="Database name")
    min_pool_size: int = Field(default=5, description="Minimum pool size")
    max_pool_size: int = Field(default=20, description="Maximum pool size")

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        """Load from environment variables"""
        return cls(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            user=os.getenv("DB_USER", "ai_user"),
            password=os.getenv("DB_PASSWORD", ""),
            database=os.getenv("DB_NAME", "ai_platform"),
            min_pool_size=int(os.getenv("DB_MIN_POOL_SIZE", "5")),
            max_pool_size=int(os.getenv("DB_MAX_POOL_SIZE", "20")),
        )


class EmbeddingConfig(BaseModel):
    """Embedding model configuration"""
    model_name: str = Field(
        default="paraphrase-multilingual-MiniLM-L12-v2",
        description="Sentence transformer model name"
    )
    device: Optional[str] = Field(default=None, description="Device (cpu/cuda)")
    cache_folder: Optional[str] = Field(default=None, description="Model cache folder")

    @classmethod
    def from_env(cls) -> "EmbeddingConfig":
        """Load from environment variables"""
        return cls(
            model_name=os.getenv(
                "EMBEDDING_MODEL",
                "paraphrase-multilingual-MiniLM-L12-v2"
            ),
            device=os.getenv("EMBEDDING_DEVICE"),
            cache_folder=os.getenv("EMBEDDING_CACHE_FOLDER"),
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
    use_pgvector: bool = Field(
        default=False,
        description="Use pgvector extension for better performance"
    )

    @classmethod
    def from_env(cls) -> "VectorSearchConfig":
        """Load from environment variables"""
        return cls(
            use_pgvector=os.getenv("USE_PGVECTOR", "false").lower() == "true",
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


class AppConfig(BaseModel):
    """Application configuration"""
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    quota: QuotaConfig = Field(default_factory=QuotaConfig)
    vector_search: VectorSearchConfig = Field(default_factory=VectorSearchConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)

    enable_audit_log: bool = Field(default=True, description="Enable audit logging")

    @classmethod
    def from_env(cls) -> "AppConfig":
        """Load all configuration from environment variables"""
        return cls(
            database=DatabaseConfig.from_env(),
            embedding=EmbeddingConfig.from_env(),
            quota=QuotaConfig.from_env(),
            vector_search=VectorSearchConfig.from_env(),
            server=ServerConfig.from_env(),
            enable_audit_log=os.getenv("ENABLE_AUDIT_LOG", "true").lower() == "true",
        )

    def print_summary(self):
        """Print configuration summary"""
        print("=" * 60)
        print("AI Runtime Configuration")
        print("=" * 60)
        print(f"Database: {self.database.host}:{self.database.port}/{self.database.database}")
        print(f"Embedding Model: {self.embedding.model_name}")
        print(f"Max Documents/Tenant: {self.quota.max_documents_per_tenant}")
        print(f"Use pgvector: {self.vector_search.use_pgvector}")
        print(f"Audit Log: {'Enabled' if self.enable_audit_log else 'Disabled'}")
        print(f"Server: {self.server.host}:{self.server.http_port}")
        print("=" * 60)


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
