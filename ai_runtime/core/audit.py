"""
Audit Logging Service
"""
import uuid
import logging
from datetime import datetime
from typing import Optional, Dict, Any
import asyncpg
import json

logger = logging.getLogger(__name__)


class AuditLogger:
    """Audit logging service"""

    def __init__(self, db_pool: asyncpg.Pool, enabled: bool = True):
        """
        Initialize audit logger

        Args:
            db_pool: Database connection pool
            enabled: Whether audit logging is enabled
        """
        self.db_pool = db_pool
        self.enabled = enabled

    async def log(
        self,
        action: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ):
        """
        Log an audit event

        Args:
            action: Action performed (e.g., "create", "update", "delete", "search")
            resource_type: Type of resource (e.g., "document", "user")
            resource_id: ID of the resource
            user_id: User who performed the action
            tenant_id: Tenant ID
            details: Additional details (JSON)
            ip_address: Client IP address
            user_agent: Client user agent
        """
        if not self.enabled:
            return

        try:
            query = """
                INSERT INTO audit_logs (
                    id, user_id, tenant_id, action, resource_type, resource_id,
                    ip_address, user_agent, details, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """

            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    query,
                    str(uuid.uuid4()),
                    user_id,
                    tenant_id,
                    action,
                    resource_type,
                    resource_id,
                    ip_address,
                    user_agent,
                    json.dumps(details or {}),
                    datetime.utcnow(),
                )

            logger.debug(
                f"Audit: {action} {resource_type} {resource_id} by {user_id or 'anonymous'}"
            )

        except Exception as e:
            # Don't fail the main operation if audit logging fails
            logger.error(f"Failed to write audit log: {e}")

    async def log_document_create(
        self,
        document_id: str,
        tenant_id: str,
        user_id: Optional[str],
        title: str,
        source_type: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ):
        """Log document creation"""
        await self.log(
            action="document.create",
            resource_type="document",
            resource_id=document_id,
            user_id=user_id,
            tenant_id=tenant_id,
            details={
                "title": title,
                "source_type": source_type,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def log_document_update(
        self,
        document_id: str,
        tenant_id: str,
        user_id: Optional[str],
        changes: Dict[str, Any],
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ):
        """Log document update"""
        await self.log(
            action="document.update",
            resource_type="document",
            resource_id=document_id,
            user_id=user_id,
            tenant_id=tenant_id,
            details={"changes": changes},
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def log_document_delete(
        self,
        document_id: str,
        tenant_id: str,
        user_id: Optional[str],
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ):
        """Log document deletion"""
        await self.log(
            action="document.delete",
            resource_type="document",
            resource_id=document_id,
            user_id=user_id,
            tenant_id=tenant_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def log_document_search(
        self,
        tenant_id: str,
        user_id: Optional[str],
        query: str,
        results_count: int,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ):
        """Log document search"""
        await self.log(
            action="document.search",
            resource_type="document",
            user_id=user_id,
            tenant_id=tenant_id,
            details={
                "query": query,
                "results_count": results_count,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def log_file_upload(
        self,
        document_id: str,
        tenant_id: str,
        user_id: Optional[str],
        filename: str,
        file_size: int,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ):
        """Log file upload"""
        await self.log(
            action="document.upload",
            resource_type="document",
            resource_id=document_id,
            user_id=user_id,
            tenant_id=tenant_id,
            details={
                "filename": filename,
                "file_size": file_size,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def log_url_fetch(
        self,
        document_id: str,
        tenant_id: str,
        user_id: Optional[str],
        url: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ):
        """Log URL fetch"""
        await self.log(
            action="document.url_fetch",
            resource_type="document",
            resource_id=document_id,
            user_id=user_id,
            tenant_id=tenant_id,
            details={"url": url},
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def log_batch_create(
        self,
        tenant_id: str,
        user_id: Optional[str],
        total_count: int,
        success_count: int,
        failed_count: int,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ):
        """Log batch create operation"""
        await self.log(
            action="document.batch_create",
            resource_type="document",
            user_id=user_id,
            tenant_id=tenant_id,
            details={
                "total_count": total_count,
                "success_count": success_count,
                "failed_count": failed_count,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )
