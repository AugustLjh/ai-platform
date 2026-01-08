"""
Quota Management Service
"""
import logging
from typing import Optional
import asyncpg
from fastapi import HTTPException

from .config import QuotaConfig

logger = logging.getLogger(__name__)


class QuotaError(Exception):
    """Quota limit exceeded error"""
    pass


class QuotaManager:
    """Quota management service"""

    def __init__(self, db_pool: asyncpg.Pool, config: QuotaConfig):
        """
        Initialize quota manager

        Args:
            db_pool: Database connection pool
            config: Quota configuration
        """
        self.db_pool = db_pool
        self.config = config

    async def check_document_quota(self, tenant_id: str) -> bool:
        """
        Check if tenant can create more documents

        Args:
            tenant_id: Tenant ID

        Returns:
            True if within quota, False otherwise

        Raises:
            QuotaError: If quota exceeded
        """
        query = """
            SELECT COUNT(*) FROM documents WHERE tenant_id = $1
        """

        async with self.db_pool.acquire() as conn:
            count = await conn.fetchval(query, tenant_id)

        if count >= self.config.max_documents_per_tenant:
            raise QuotaError(
                f"Document quota exceeded: {count}/{self.config.max_documents_per_tenant}. "
                f"Please contact support to increase your limit."
            )

        return True

    async def check_document_size(self, content: str) -> bool:
        """
        Check if document content size is within limits

        Args:
            content: Document content

        Returns:
            True if within limits

        Raises:
            QuotaError: If size exceeded
        """
        size = len(content.encode('utf-8'))

        if size > self.config.max_document_size:
            raise QuotaError(
                f"Document size exceeded: {size} bytes > {self.config.max_document_size} bytes. "
                f"Maximum allowed: {self.config.max_document_size / 1024 / 1024:.1f}MB"
            )

        return True

    async def check_upload_size(self, file_size: int) -> bool:
        """
        Check if upload file size is within limits

        Args:
            file_size: File size in bytes

        Returns:
            True if within limits

        Raises:
            QuotaError: If size exceeded
        """
        if file_size > self.config.max_upload_file_size:
            raise QuotaError(
                f"Upload file size exceeded: {file_size} bytes > {self.config.max_upload_file_size} bytes. "
                f"Maximum allowed: {self.config.max_upload_file_size / 1024 / 1024:.1f}MB"
            )

        return True

    async def get_tenant_usage(self, tenant_id: str) -> dict:
        """
        Get tenant usage statistics

        Args:
            tenant_id: Tenant ID

        Returns:
            Dictionary with usage statistics
        """
        query = """
            SELECT
                COUNT(*) as total_documents,
                SUM(LENGTH(content)) as total_size,
                COUNT(CASE WHEN indexed THEN 1 END) as indexed_documents
            FROM documents
            WHERE tenant_id = $1
        """

        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(query, tenant_id)

        return {
            "total_documents": row["total_documents"] or 0,
            "total_size": row["total_size"] or 0,
            "indexed_documents": row["indexed_documents"] or 0,
            "max_documents": self.config.max_documents_per_tenant,
            "max_document_size": self.config.max_document_size,
            "max_upload_size": self.config.max_upload_file_size,
            "quota_used_percent": (
                (row["total_documents"] or 0) / self.config.max_documents_per_tenant * 100
                if self.config.max_documents_per_tenant > 0 else 0
            ),
        }

    async def update_quota_tracking(self, tenant_id: str):
        """
        Update quota tracking in quotas table

        Args:
            tenant_id: Tenant ID
        """
        try:
            # Get current usage
            usage = await self.get_tenant_usage(tenant_id)

            # Update quotas table
            query = """
                INSERT INTO quotas (tenant_id, quota_type, limit_value, current_value, period_start, period_end)
                VALUES ($1, 'documents', $2, $3, NOW(), NOW() + INTERVAL '1 month')
                ON CONFLICT (tenant_id, quota_type)
                DO UPDATE SET
                    current_value = $3,
                    updated_at = NOW()
            """

            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    query,
                    tenant_id,
                    self.config.max_documents_per_tenant,
                    usage["total_documents"],
                )

        except Exception as e:
            # Don't fail the main operation if quota tracking fails
            logger.error(f"Failed to update quota tracking: {e}")


def convert_quota_error_to_http_exception(error: QuotaError) -> HTTPException:
    """
    Convert QuotaError to HTTPException

    Args:
        error: QuotaError instance

    Returns:
        HTTPException with 429 status code
    """
    return HTTPException(
        status_code=429,  # Too Many Requests
        detail=str(error),
        headers={"Retry-After": "3600"},  # Retry after 1 hour
    )
