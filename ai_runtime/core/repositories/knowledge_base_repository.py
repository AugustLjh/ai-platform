"""
Knowledge Base Repository
Handles database operations for knowledge bases
"""
import logging
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
import asyncpg

from ..models.knowledge_base import KnowledgeBase, AccessLevel

logger = logging.getLogger(__name__)


class KnowledgeBaseRepository:
    """知识库数据访问层"""

    def __init__(self, db_pool: asyncpg.Pool):
        self.db_pool = db_pool

    async def create_knowledge_base(
        self,
        tenant_id: str,
        name: str,
        description: Optional[str] = None,
        user_id: Optional[str] = None,
        access_level: AccessLevel = AccessLevel.TENANT,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> KnowledgeBase:
        """创建知识库"""
        import json

        query = """
            INSERT INTO knowledge_bases (
                tenant_id, user_id, name, description, access_level, metadata
            )
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id, tenant_id, user_id, name, description, access_level,
                      created_at, updated_at, metadata
        """

        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                tenant_id,
                user_id,
                name,
                description,
                access_level.value,
                json.dumps(metadata or {})
            )

            return self._row_to_knowledge_base(row)

    async def get_knowledge_base(
        self,
        kb_id: str,
        tenant_id: str,
        user_id: Optional[str] = None
    ) -> Optional[KnowledgeBase]:
        """获取知识库（带权限检查）"""
        query = """
            SELECT id, tenant_id, user_id, name, description, access_level,
                   created_at, updated_at, metadata
            FROM knowledge_bases
            WHERE id = $1 AND tenant_id = $2
              AND (access_level = 'tenant' OR (access_level = 'user' AND user_id = $3))
        """

        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(query, kb_id, tenant_id, user_id)

            if row:
                return self._row_to_knowledge_base(row)
            return None

    async def update_knowledge_base(
        self,
        kb_id: str,
        tenant_id: str,
        user_id: Optional[str] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[KnowledgeBase]:
        """更新知识库"""
        import json

        # Build dynamic update query
        updates = []
        params = [kb_id, tenant_id, user_id]
        param_idx = 4

        if name is not None:
            updates.append(f"name = ${param_idx}")
            params.append(name)
            param_idx += 1

        if description is not None:
            updates.append(f"description = ${param_idx}")
            params.append(description)
            param_idx += 1

        if metadata is not None:
            updates.append(f"metadata = ${param_idx}")
            params.append(json.dumps(metadata))
            param_idx += 1

        if not updates:
            # No updates, just return current state
            return await self.get_knowledge_base(kb_id, tenant_id, user_id)

        query = f"""
            UPDATE knowledge_bases
            SET {', '.join(updates)}
            WHERE id = $1 AND tenant_id = $2
              AND (access_level = 'tenant' OR (access_level = 'user' AND user_id = $3))
            RETURNING id, tenant_id, user_id, name, description, access_level,
                      created_at, updated_at, metadata
        """

        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(query, *params)

            if row:
                return self._row_to_knowledge_base(row)
            return None

    async def delete_knowledge_base(
        self,
        kb_id: str,
        tenant_id: str,
        user_id: Optional[str] = None
    ) -> bool:
        """删除知识库（级联删除所有文档）"""
        query = """
            DELETE FROM knowledge_bases
            WHERE id = $1 AND tenant_id = $2
              AND (access_level = 'tenant' OR (access_level = 'user' AND user_id = $3))
        """

        async with self.db_pool.acquire() as conn:
            result = await conn.execute(query, kb_id, tenant_id, user_id)

            # asyncpg returns "DELETE N" where N is number of rows
            try:
                rows_deleted = int(result.split()[-1])
                return rows_deleted > 0
            except (ValueError, IndexError):
                logger.error(f"Unexpected DELETE result format: {result}")
                return False

    async def list_knowledge_bases(
        self,
        tenant_id: str,
        user_id: Optional[str] = None,
        access_level: Optional[AccessLevel] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[KnowledgeBase], int]:
        """列出知识库（分页）"""
        # Build WHERE clause
        where_clauses = ["tenant_id = $1"]
        params = [tenant_id]
        param_idx = 2

        # Permission filter
        where_clauses.append(
            f"(access_level = 'tenant' OR (access_level = 'user' AND user_id = ${param_idx}))"
        )
        params.append(user_id)
        param_idx += 1

        # Optional access level filter
        if access_level:
            where_clauses.append(f"access_level = ${param_idx}")
            params.append(access_level.value)
            param_idx += 1

        where_clause = " AND ".join(where_clauses)

        # Count query
        count_query = f"""
            SELECT COUNT(*) FROM knowledge_bases
            WHERE {where_clause}
        """

        # List query with pagination
        offset = (page - 1) * page_size
        list_query = f"""
            SELECT id, tenant_id, user_id, name, description, access_level,
                   created_at, updated_at, metadata
            FROM knowledge_bases
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """

        async with self.db_pool.acquire() as conn:
            # Get total count
            total = await conn.fetchval(count_query, *params)

            # Get paginated results
            rows = await conn.fetch(list_query, *params, page_size, offset)

            knowledge_bases = [self._row_to_knowledge_base(row) for row in rows]

            return knowledge_bases, total

    async def get_knowledge_base_stats(
        self,
        kb_id: str,
        tenant_id: str,
        user_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """获取知识库统计信息"""
        query = """
            SELECT
                kb.id,
                kb.tenant_id,
                kb.user_id,
                kb.name,
                kb.description,
                kb.access_level,
                kb.created_at,
                kb.updated_at,
                kb.metadata,
                COUNT(d.id) as document_count
            FROM knowledge_bases kb
            LEFT JOIN documents d ON d.knowledge_base_id = kb.id
            WHERE kb.id = $1 AND kb.tenant_id = $2
              AND (kb.access_level = 'tenant' OR (kb.access_level = 'user' AND kb.user_id = $3))
            GROUP BY kb.id, kb.tenant_id, kb.user_id, kb.name, kb.description,
                     kb.access_level, kb.created_at, kb.updated_at, kb.metadata
        """

        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(query, kb_id, tenant_id, user_id)

            if row:
                kb = self._row_to_knowledge_base(row)
                return {
                    **kb.to_dict(),
                    "document_count": row["document_count"]
                }
            return None

    async def list_knowledge_bases_with_stats(
        self,
        tenant_id: str,
        user_id: Optional[str] = None,
        access_level: Optional[AccessLevel] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """列出知识库（带统计信息）"""
        # Build WHERE clause
        where_clauses = ["kb.tenant_id = $1"]
        params = [tenant_id]
        param_idx = 2

        # Permission filter
        where_clauses.append(
            f"(kb.access_level = 'tenant' OR (kb.access_level = 'user' AND kb.user_id = ${param_idx}))"
        )
        params.append(user_id)
        param_idx += 1

        # Optional access level filter
        if access_level:
            where_clauses.append(f"kb.access_level = ${param_idx}")
            params.append(access_level.value)
            param_idx += 1

        where_clause = " AND ".join(where_clauses)

        # Count query
        count_query = f"""
            SELECT COUNT(*) FROM knowledge_bases kb
            WHERE {where_clause}
        """

        # List query with stats
        offset = (page - 1) * page_size
        list_query = f"""
            SELECT
                kb.id,
                kb.tenant_id,
                kb.user_id,
                kb.name,
                kb.description,
                kb.access_level,
                kb.created_at,
                kb.updated_at,
                kb.metadata,
                COUNT(d.id) as document_count
            FROM knowledge_bases kb
            LEFT JOIN documents d ON d.knowledge_base_id = kb.id
            WHERE {where_clause}
            GROUP BY kb.id, kb.tenant_id, kb.user_id, kb.name, kb.description,
                     kb.access_level, kb.created_at, kb.updated_at, kb.metadata
            ORDER BY kb.created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """

        async with self.db_pool.acquire() as conn:
            # Get total count
            total = await conn.fetchval(count_query, *params)

            # Get paginated results with stats
            rows = await conn.fetch(list_query, *params, page_size, offset)

            results = []
            for row in rows:
                kb = self._row_to_knowledge_base(row)
                results.append({
                    **kb.to_dict(),
                    "document_count": row["document_count"]
                })

            return results, total

    def _row_to_knowledge_base(self, row: asyncpg.Record) -> KnowledgeBase:
        """将数据库行转换为KnowledgeBase对象"""
        import json

        # Parse metadata if it's a string
        metadata = row["metadata"]
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Failed to parse metadata JSON: {e}")
                metadata = {}

        return KnowledgeBase(
            id=str(row["id"]),
            tenant_id=str(row["tenant_id"]),
            user_id=str(row["user_id"]) if row["user_id"] else None,
            name=row["name"],
            description=row["description"],
            access_level=AccessLevel(row["access_level"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=metadata or {}
        )
