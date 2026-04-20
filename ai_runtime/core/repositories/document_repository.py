"""
Document Repository - Database Access Layer
"""
import json
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
import asyncpg
from ai_runtime.core.models.knowledge_base import (
    Document,
    SourceType,
    AccessLevel,
    utc_now,
)


class DocumentRepository:
    """文档数据库访问层"""

    def __init__(self, db_pool: asyncpg.Pool):
        """
        初始化仓库

        Args:
            db_pool: asyncpg 连接池
        """
        self.db_pool = db_pool

    async def create_document(
        self,
        tenant_id: str,
        title: str,
        content: str,
        knowledge_base_id: str,
        user_id: Optional[str] = None,
        access_level: AccessLevel = AccessLevel.TENANT,
        source: Optional[str] = None,
        source_type: SourceType = SourceType.MANUAL,
        embedding_model: Optional[str] = None,
        embedding_model_key: Optional[str] = None,
        embedding_dimension: Optional[int] = None,
        index_status: str = "pending",
        index_version: int = 1,
        last_index_error: Optional[str] = None,
        indexed: bool = False,
        search_terms: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        conn: Optional[asyncpg.Connection] = None,
    ) -> Document:
        """
        创建文档

        Args:
            tenant_id: 租户ID
            title: 文档标题
            content: 文档内容
            knowledge_base_id: 所属知识库ID
            user_id: 用户ID（私有文档）
            access_level: 访问级别
            source: 来源
            source_type: 来源类型
            embedding_model: 嵌入模型名称
            metadata: 额外元数据

        Returns:
            创建的文档对象
        """
        doc_id = str(uuid.uuid4())
        indexed_at = utc_now() if indexed else None
        now = utc_now()

        query = """
            INSERT INTO documents (
                id, tenant_id, user_id, knowledge_base_id, access_level, title, content,
                source, source_type, embedding_model, embedding_model_key, embedding_dimension,
                search_terms, indexed, indexed_at, index_status, index_version,
                last_index_error, created_at, updated_at, metadata
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14,
                $15, $16, $17, $18, $19, $20, $21
            )
            RETURNING *
        """

        if conn is None:
            async with self.db_pool.acquire() as pool_conn:
                row = await pool_conn.fetchrow(
                    query,
                    doc_id,
                    tenant_id,
                    user_id,
                    knowledge_base_id,
                    access_level.value,
                    title,
                    content,
                    source,
                    source_type.value,
                    embedding_model,
                    embedding_model_key,
                    embedding_dimension,
                    search_terms or "",
                    indexed,
                    indexed_at,
                    index_status,
                    index_version,
                    last_index_error,
                    now,
                    now,
                    json.dumps(metadata or {}),
                )
        else:
            row = await conn.fetchrow(
                query,
                doc_id,
                tenant_id,
                user_id,
                knowledge_base_id,
                access_level.value,
                title,
                content,
                source,
                source_type.value,
                embedding_model,
                embedding_model_key,
                embedding_dimension,
                search_terms or "",
                indexed,
                indexed_at,
                index_status,
                index_version,
                last_index_error,
                now,
                now,
                json.dumps(metadata or {}),
            )

        return self._row_to_document(row)

    async def get_document(
        self,
        document_id: str,
        tenant_id: str,
        user_id: Optional[str] = None,
    ) -> Optional[Document]:
        """
        获取文档（含权限检查）

        Args:
            document_id: 文档ID
            tenant_id: 租户ID
            user_id: 用户ID

        Returns:
            文档对象，如果不存在或无权限则返回None
        """
        query = """
            SELECT * FROM documents
            WHERE id = $1 AND tenant_id = $2
            AND (
                access_level = 'tenant'
                OR (access_level = 'user' AND user_id = $3)
            )
        """

        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(query, document_id, tenant_id, user_id)

        return self._row_to_document(row) if row else None

    async def update_document(
        self,
        document_id: str,
        tenant_id: str,
        user_id: Optional[str] = None,
        title: Optional[str] = None,
        content: Optional[str] = None,
        source: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        embedding_model: Optional[str] = None,
        embedding_model_key: Optional[str] = None,
        embedding_dimension: Optional[int] = None,
        indexed: Optional[bool] = None,
        index_status: Optional[str] = None,
        index_version: Optional[int] = None,
        last_index_error: Optional[str] = None,
        search_terms: Optional[str] = None,
        conn: Optional[asyncpg.Connection] = None,
    ) -> Optional[Document]:
        """
        更新文档

        Args:
            document_id: 文档ID
            tenant_id: 租户ID
            user_id: 用户ID
            title: 新标题
            content: 新内容
            source: 新来源
            metadata: 新元数据
            embedding_model: 嵌入模型

        Returns:
            更新后的文档，如果不存在或无权限则返回None
        """
        # 构建动态更新字段
        updates = ["updated_at = $1"]
        params = [utc_now()]
        param_idx = 2

        if title is not None:
            updates.append(f"title = ${param_idx}")
            params.append(title)
            param_idx += 1

        if content is not None:
            updates.append(f"content = ${param_idx}")
            params.append(content)
            param_idx += 1

        if source is not None:
            updates.append(f"source = ${param_idx}")
            params.append(source)
            param_idx += 1

        if metadata is not None:
            updates.append(f"metadata = ${param_idx}")
            params.append(json.dumps(metadata))
            param_idx += 1

        if search_terms is not None:
            updates.append(f"search_terms = ${param_idx}")
            params.append(search_terms)
            param_idx += 1

        if embedding_model is not None:
            updates.append(f"embedding_model = ${param_idx}")
            params.append(embedding_model)
            param_idx += 1

        if embedding_model_key is not None:
            updates.append(f"embedding_model_key = ${param_idx}")
            params.append(embedding_model_key)
            param_idx += 1

        if embedding_dimension is not None:
            updates.append(f"embedding_dimension = ${param_idx}")
            params.append(embedding_dimension)
            param_idx += 1

        if indexed is not None:
            updates.append(f"indexed = ${param_idx}")
            params.append(indexed)
            param_idx += 1

            updates.append(f"indexed_at = ${param_idx}")
            params.append(utc_now() if indexed else None)
            param_idx += 1

        if index_status is not None:
            updates.append(f"index_status = ${param_idx}")
            params.append(index_status)
            param_idx += 1

        if index_version is not None:
            updates.append(f"index_version = ${param_idx}")
            params.append(index_version)
            param_idx += 1

        if last_index_error is not None:
            updates.append(f"last_index_error = ${param_idx}")
            params.append(last_index_error)
            param_idx += 1

        # 添加WHERE条件参数
        params.extend([document_id, tenant_id, user_id])

        query = f"""
            UPDATE documents
            SET {', '.join(updates)}
            WHERE id = ${param_idx} AND tenant_id = ${param_idx + 1}
            AND (
                access_level = 'tenant'
                OR (access_level = 'user' AND user_id = ${param_idx + 2})
            )
            RETURNING *
        """

        if conn is None:
            async with self.db_pool.acquire() as pool_conn:
                row = await pool_conn.fetchrow(query, *params)
        else:
            row = await conn.fetchrow(query, *params)

        return self._row_to_document(row) if row else None

    async def replace_document_chunks(
        self,
        document: Document,
        chunks: List[Dict[str, Any]],
        conn: Optional[asyncpg.Connection] = None,
    ) -> None:
        delete_query = "DELETE FROM document_chunks WHERE document_id = $1"
        insert_query = """
            INSERT INTO document_chunks (
                document_id, tenant_id, knowledge_base_id, user_id, access_level,
                chunk_index, start_offset, end_offset, char_count, title, content,
                source, source_type, chunk_hash, search_terms,
                metadata, created_at, updated_at
            ) VALUES (
                $1, $2, $3, $4, $5,
                $6, $7, $8, $9, $10, $11,
                $12, $13, $14, $15,
                $16, $17, $18
            )
        """

        target_conn = conn
        owned_conn = False
        if target_conn is None:
            target_conn = await self.db_pool.acquire()
            owned_conn = True

        try:
            await target_conn.execute(delete_query, document.id)

            if not chunks:
                return

            now = utc_now()
            rows = [
                (
                    document.id,
                    document.tenant_id,
                    document.knowledge_base_id,
                    document.user_id,
                    document.access_level.value,
                    int(chunk["chunk_index"]),
                    int(chunk["start_offset"]),
                    int(chunk["end_offset"]),
                    int(chunk["char_count"]),
                    document.title,
                    chunk["content"],
                    document.source,
                    document.source_type.value,
                    chunk.get("chunk_hash"),
                    chunk.get("search_terms") or "",
                    json.dumps(chunk.get("metadata") or {}),
                    now,
                    now,
                )
                for chunk in chunks
            ]
            await target_conn.executemany(insert_query, rows)
        finally:
            if owned_conn and target_conn is not None:
                await self.db_pool.release(target_conn)

    async def delete_document(
        self,
        document_id: str,
        tenant_id: str,
        user_id: Optional[str] = None,
    ) -> bool:
        """
        删除文档

        Args:
            document_id: 文档ID
            tenant_id: 租户ID
            user_id: 用户ID

        Returns:
            是否删除成功
        """
        query = """
            DELETE FROM documents
            WHERE id = $1 AND tenant_id = $2
            AND (
                access_level = 'tenant'
                OR (access_level = 'user' AND user_id = $3)
            )
        """

        async with self.db_pool.acquire() as conn:
            result = await conn.execute(query, document_id, tenant_id, user_id)

        # 解析 "DELETE N" 字符串
        deleted_count = int(result.split()[-1])
        return deleted_count > 0

    async def list_documents(
        self,
        tenant_id: str,
        user_id: Optional[str] = None,
        knowledge_base_id: Optional[str] = None,
        access_level: Optional[AccessLevel] = None,
        source_type: Optional[SourceType] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[List[Document], int]:
        """
        列出文档（分页）

        Args:
            tenant_id: 租户ID
            user_id: 用户ID
            knowledge_base_id: 筛选知识库ID
            access_level: 筛选访问级别
            source_type: 筛选来源类型
            page: 页码（从1开始）
            page_size: 每页数量

        Returns:
            (文档列表, 总数)
        """
        conditions = ["tenant_id = $1"]
        params = [tenant_id]
        param_idx = 2

        # 权限过滤
        if access_level:
            conditions.append(f"access_level = ${param_idx}")
            params.append(access_level.value)
            param_idx += 1
        else:
            # 用户可以看到租户级别的文档 + 自己的私有文档
            conditions.append(f"(access_level = 'tenant' OR (access_level = 'user' AND user_id = ${param_idx}))")
            params.append(user_id)
            param_idx += 1

        # 知识库过滤
        if knowledge_base_id:
            conditions.append(f"knowledge_base_id = ${param_idx}")
            params.append(knowledge_base_id)
            param_idx += 1

        # 来源类型过滤
        if source_type:
            conditions.append(f"source_type = ${param_idx}")
            params.append(source_type.value)
            param_idx += 1

        where_clause = " AND ".join(conditions)

        # 查询总数
        count_query = f"SELECT COUNT(*) FROM documents WHERE {where_clause}"

        # 查询数据（分页）
        offset = (page - 1) * page_size
        data_query = f"""
            SELECT * FROM documents
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """
        params.extend([page_size, offset])

        async with self.db_pool.acquire() as conn:
            total = await conn.fetchval(count_query, *params[:param_idx - 1])
            rows = await conn.fetch(data_query, *params)

        documents = [self._row_to_document(row) for row in rows]
        return documents, total

    async def get_documents_by_ids(
        self,
        document_ids: List[str],
        tenant_id: str,
        user_id: Optional[str] = None,
    ) -> Dict[str, Document]:
        """批量获取文档并保留权限过滤。"""
        if not document_ids:
            return {}

        ids = [uuid.UUID(document_id) for document_id in document_ids]
        query = """
            SELECT *
            FROM documents
            WHERE tenant_id = $1
              AND id = ANY($2::uuid[])
              AND (
                    access_level = 'tenant'
                    OR (access_level = 'user' AND user_id = $3)
              )
        """

        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query, tenant_id, ids, user_id)

        return {
            str(row["id"]): self._row_to_document(row)
            for row in rows
        }

    async def get_document_chunks_for_indexing(
        self,
        document_id: str,
        tenant_id: str,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """获取用于向量索引构建的完整 chunk 数据。"""
        query = """
            SELECT
                id,
                chunk_index,
                start_offset,
                end_offset,
                char_count,
                content,
                search_terms,
                metadata,
                chunk_hash
            FROM document_chunks
            WHERE document_id = $1
              AND tenant_id = $2
              AND (
                    access_level = 'tenant'
                    OR (access_level = 'user' AND user_id = $3)
              )
            ORDER BY chunk_index ASC
        """

        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query, document_id, tenant_id, user_id)

        chunks: List[Dict[str, Any]] = []
        for row in rows:
            metadata = row["metadata"]
            if isinstance(metadata, str):
                metadata = json.loads(metadata)

            chunks.append(
                {
                    "chunk_id": str(row["id"]),
                    "chunk_index": int(row["chunk_index"]),
                    "start_offset": int(row["start_offset"]),
                    "end_offset": int(row["end_offset"]),
                    "char_count": int(row["char_count"]),
                    "content": row["content"],
                    "search_terms": row["search_terms"] or "",
                    "metadata": metadata or {},
                    "chunk_hash": row["chunk_hash"],
                }
            )
        return chunks

    async def list_documents_for_vector_backfill(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        tenant_id: Optional[str] = None,
        knowledge_base_id: Optional[str] = None,
    ) -> List[Document]:
        """列出用于向量回填的文档，不做权限过滤。"""
        conditions: List[str] = []
        params: List[Any] = []
        param_idx = 1

        if tenant_id:
            conditions.append(f"tenant_id = ${param_idx}")
            params.append(tenant_id)
            param_idx += 1

        if knowledge_base_id:
            conditions.append(f"knowledge_base_id = ${param_idx}")
            params.append(knowledge_base_id)
            param_idx += 1

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"""
            SELECT *
            FROM documents
            {where_clause}
            ORDER BY created_at ASC, id ASC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """
        params.extend([limit, offset])

        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        return [self._row_to_document(row) for row in rows]

    async def get_document_for_indexing(self, document_id: str) -> Optional[Document]:
        query = "SELECT * FROM documents WHERE id = $1"
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(query, document_id)
        return self._row_to_document(row) if row else None

    async def enqueue_index_job(
        self,
        *,
        tenant_id: str,
        knowledge_base_id: Optional[str],
        document_id: str,
        job_type: str,
        target_version: Optional[int],
        payload: Optional[Dict[str, Any]] = None,
        conn: Optional[asyncpg.Connection] = None,
    ) -> None:
        query = """
            INSERT INTO document_index_jobs (
                tenant_id, knowledge_base_id, document_id, job_type, target_version,
                status, attempts, next_run_at, payload
            ) VALUES ($1, $2, $3, $4, $5, 'pending', 0, NOW(), $6)
        """
        args = (
            tenant_id,
            knowledge_base_id,
            document_id,
            job_type,
            target_version,
            json.dumps(payload or {}),
        )
        if conn is None:
            async with self.db_pool.acquire() as pool_conn:
                await pool_conn.execute(query, *args)
        else:
            await conn.execute(query, *args)

    async def claim_index_jobs(self, limit: int = 10) -> List[Dict[str, Any]]:
        query = """
            WITH selected AS (
                SELECT id
                FROM document_index_jobs
                WHERE status IN ('pending', 'retry')
                  AND next_run_at <= NOW()
                ORDER BY created_at ASC
                LIMIT $1
                FOR UPDATE SKIP LOCKED
            )
            UPDATE document_index_jobs jobs
            SET status = 'running',
                attempts = jobs.attempts + 1,
                started_at = NOW(),
                updated_at = NOW()
            FROM selected
            WHERE jobs.id = selected.id
            RETURNING jobs.*
        """
        async with self.db_pool.acquire() as conn:
            async with conn.transaction():
                rows = await conn.fetch(query, limit)
        return [self._row_to_index_job(row) for row in rows]

    async def mark_index_job_completed(self, job_id: str) -> None:
        query = """
            UPDATE document_index_jobs
            SET status = 'completed',
                completed_at = NOW(),
                last_error = NULL,
                updated_at = NOW()
            WHERE id = $1
        """
        async with self.db_pool.acquire() as conn:
            await conn.execute(query, job_id)

    async def mark_index_job_retry(
        self,
        job_id: str,
        error: str,
        delay_seconds: int = 30,
    ) -> None:
        query = """
            UPDATE document_index_jobs
            SET status = 'retry',
                last_error = $2,
                next_run_at = NOW() + ($3::text || ' seconds')::interval,
                updated_at = NOW()
            WHERE id = $1
        """
        async with self.db_pool.acquire() as conn:
            await conn.execute(query, job_id, error[:4000], max(1, delay_seconds))

    async def mark_index_job_failed(self, job_id: str, error: str) -> None:
        query = """
            UPDATE document_index_jobs
            SET status = 'failed',
                last_error = $2,
                completed_at = NOW(),
                updated_at = NOW()
            WHERE id = $1
        """
        async with self.db_pool.acquire() as conn:
            await conn.execute(query, job_id, error[:4000])

    async def update_document_index_state(
        self,
        *,
        document_id: str,
        index_status: str,
        indexed: bool,
        indexed_at: Optional[datetime],
        last_index_error: Optional[str],
    ) -> None:
        query = """
            UPDATE documents
            SET index_status = $2,
                indexed = $3,
                indexed_at = $4,
                last_index_error = $5,
                updated_at = NOW()
            WHERE id = $1
        """
        async with self.db_pool.acquire() as conn:
            await conn.execute(query, document_id, index_status, indexed, indexed_at, last_index_error)

    async def search_by_embedding(
        self,
        tenant_id: str,
        query_embedding: List[float],
        user_id: Optional[str] = None,
        top_k: int = 5,
        knowledge_base_id: Optional[str] = None,
        access_level: Optional[AccessLevel] = None,
        source_type: Optional[SourceType] = None,
    ) -> List[tuple[Document, float]]:
        """
        基于向量相似度搜索文档

        向量检索现在统一由 Qdrant 承担；仓库层只保留 PostgreSQL 元数据与关键词检索。

        Args:
            tenant_id: 租户ID
            query_embedding: 查询向量
            user_id: 用户ID
            top_k: 返回结果数量
            knowledge_base_id: 筛选知识库ID
            access_level: 筛选访问级别
            source_type: 筛选来源类型

        Returns:
            [(文档, 相似度分数), ...]，按分数降序排列
        """
        raise NotImplementedError(
            "Vector similarity search is handled by Qdrant through DocumentService.vector_index; "
            "DocumentRepository only supports PostgreSQL metadata and keyword queries."
        )

    async def search_by_keyword(
        self,
        tenant_id: str,
        query: str,
        user_id: Optional[str] = None,
        top_k: int = 5,
        knowledge_base_id: Optional[str] = None,
        access_level: Optional[AccessLevel] = None,
        source_type: Optional[SourceType] = None,
    ) -> List[tuple[Document, float]]:
        """
        基于关键词搜索文档

        Args:
            tenant_id: 租户ID
            query: 查询关键词
            user_id: 用户ID
            top_k: 返回结果数量
            knowledge_base_id: 筛选知识库ID
            access_level: 筛选访问级别
            source_type: 筛选来源类型

        Returns:
            [(文档, 相似度分数), ...]
        """
        normalized_query = query.strip()
        if not normalized_query:
            return []

        conditions = ["dc.tenant_id = $1"]
        params = [tenant_id]
        param_idx = 2

        # 权限过滤
        if access_level:
            conditions.append(f"dc.access_level = ${param_idx}")
            params.append(access_level.value)
            param_idx += 1
        else:
            conditions.append(f"(dc.access_level = 'tenant' OR (dc.access_level = 'user' AND dc.user_id = ${param_idx}))")
            params.append(user_id)
            param_idx += 1

        # 来源类型过滤
        if source_type:
            conditions.append(f"dc.source_type = ${param_idx}")
            params.append(source_type.value)
            param_idx += 1

        # 知识库过滤
        if knowledge_base_id:
            conditions.append(f"dc.knowledge_base_id = ${param_idx}")
            params.append(knowledge_base_id)
            param_idx += 1

        query_param_index = param_idx
        ts_query = f"websearch_to_tsquery('simple', ${query_param_index})"
        conditions.append(f"dc.search_vector @@ {ts_query}")
        params.append(normalized_query)
        param_idx += 1
        candidate_limit = max(top_k * 8, top_k)

        where_clause = " AND ".join(conditions)

        query_sql = f"""
            WITH ranked_chunks AS (
                SELECT
                    dc.document_id,
                    dc.chunk_index,
                    dc.start_offset,
                    dc.end_offset,
                    dc.char_count,
                    dc.content AS matched_content,
                    ts_rank(dc.search_vector, {ts_query}) AS similarity
                FROM document_chunks dc
                WHERE {where_clause}
                ORDER BY similarity DESC, dc.updated_at DESC
                LIMIT ${param_idx}
            ),
            best_chunks AS (
                SELECT DISTINCT ON (document_id)
                    document_id,
                    similarity,
                    chunk_index,
                    start_offset,
                    end_offset,
                    char_count,
                    matched_content
                FROM ranked_chunks
                ORDER BY document_id, similarity DESC, chunk_index ASC
            )
            SELECT
                d.*,
                bc.similarity,
                bc.chunk_index AS matched_chunk_index,
                bc.start_offset AS matched_start_offset,
                bc.end_offset AS matched_end_offset,
                bc.char_count AS matched_char_count,
                bc.matched_content
            FROM best_chunks bc
            JOIN documents d ON d.id = bc.document_id
            ORDER BY bc.similarity DESC, d.updated_at DESC
            LIMIT ${param_idx + 1}
        """

        params.extend([candidate_limit, top_k])

        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query_sql, *params)

        results = []
        for row in rows:
            doc = self._row_to_document(row)
            score = float(row['similarity']) if row['similarity'] is not None else 0.0
            results.append((doc, min(score, 1.0)))

        return results

    async def list_document_chunks(
        self,
        document_id: str,
        tenant_id: str,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        query = """
            SELECT
                id,
                chunk_index,
                start_offset,
                end_offset,
                char_count,
                content,
                metadata
            FROM document_chunks
            WHERE document_id = $1
              AND tenant_id = $2
              AND (
                    access_level = 'tenant'
                    OR (access_level = 'user' AND user_id = $3)
              )
            ORDER BY chunk_index ASC
        """

        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query, document_id, tenant_id, user_id)

        segments = []
        for row in rows:
            metadata = row["metadata"]
            if isinstance(metadata, str):
                metadata = json.loads(metadata)
            metadata = metadata or {}
            segments.append(
                {
                    "chunk_id": str(row["id"]),
                    "segment_index": int(row["chunk_index"]),
                    "start_offset": int(row["start_offset"]),
                    "end_offset": int(row["end_offset"]),
                    "char_count": int(row["char_count"]),
                    "content": row["content"],
                    "segment_type": metadata.get("segment_type"),
                    "section_title": metadata.get("section_title"),
                    "citation_label": metadata.get("citation_label"),
                    "heading_level": metadata.get("heading_level"),
                }
            )
        return segments

    async def search_document_chunks(
        self,
        document_id: str,
        tenant_id: str,
        user_id: Optional[str],
        query: str,
        limit: int = 3,
    ) -> List[Dict[str, Any]]:
        normalized_query = query.strip()
        if not normalized_query:
            return []

        ts_query = "websearch_to_tsquery('simple', $4)"
        query_sql = f"""
            SELECT
                id,
                chunk_index,
                start_offset,
                end_offset,
                char_count,
                content,
                metadata,
                ts_rank(search_vector, {ts_query}) AS match_score
            FROM document_chunks
            WHERE document_id = $1
              AND tenant_id = $2
              AND (
                    access_level = 'tenant'
                    OR (access_level = 'user' AND user_id = $3)
              )
              AND search_vector @@ {ts_query}
            ORDER BY match_score DESC, chunk_index ASC
            LIMIT $5
        """

        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query_sql, document_id, tenant_id, user_id, normalized_query, limit)

        segments = []
        for row in rows:
            metadata = row["metadata"]
            if isinstance(metadata, str):
                metadata = json.loads(metadata)
            metadata = metadata or {}
            segments.append(
                {
                    "chunk_id": str(row["id"]),
                    "segment_index": int(row["chunk_index"]),
                    "start_offset": int(row["start_offset"]),
                    "end_offset": int(row["end_offset"]),
                    "char_count": int(row["char_count"]),
                    "content": row["content"],
                    "match_score": float(row["match_score"]) if row["match_score"] is not None else 0.0,
                    "segment_type": metadata.get("segment_type"),
                    "section_title": metadata.get("section_title"),
                    "citation_label": metadata.get("citation_label"),
                    "heading_level": metadata.get("heading_level"),
                }
            )
        return segments

    async def find_exact_duplicate_documents(
        self,
        tenant_id: str,
        knowledge_base_id: str,
        content_hash: str,
        content: str,
        user_id: Optional[str] = None,
        limit: int = 5,
    ) -> List[Document]:
        """查询知识库内内容完全相同的文档。"""
        query = """
            SELECT *
            FROM documents
            WHERE tenant_id = $1
              AND knowledge_base_id = $2
              AND (
                    access_level = 'tenant'
                    OR (access_level = 'user' AND user_id = $3)
              )
              AND (
                    ($4 <> '' AND metadata->>'ai_content_hash' = $4)
                    OR content = $5
              )
            ORDER BY updated_at DESC
            LIMIT $6
        """

        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query, tenant_id, knowledge_base_id, user_id, content_hash, content, limit)

        return [self._row_to_document(row) for row in rows]

    async def list_documents_for_duplicate_check(
        self,
        tenant_id: str,
        knowledge_base_id: str,
        user_id: Optional[str] = None,
        limit: int = 200,
    ) -> List[Document]:
        """获取知识库内用于相似文档检测的候选文档。"""
        query = """
            SELECT *
            FROM documents
            WHERE tenant_id = $1
              AND knowledge_base_id = $2
              AND (
                    access_level = 'tenant'
                    OR (access_level = 'user' AND user_id = $3)
              )
            ORDER BY updated_at DESC
            LIMIT $4
        """

        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query, tenant_id, knowledge_base_id, user_id, limit)

        return [self._row_to_document(row) for row in rows]

    def _row_to_document(self, row) -> Document:
        """将数据库行转换为Document对象"""
        metadata = row['metadata']
        if isinstance(metadata, str):
            metadata = json.loads(metadata)

        return Document(
            id=str(row['id']),
            tenant_id=str(row['tenant_id']),
            user_id=str(row['user_id']) if row['user_id'] else None,
            knowledge_base_id=str(row['knowledge_base_id']) if row['knowledge_base_id'] else None,
            access_level=AccessLevel(row['access_level']),
            title=row['title'],
            content=row['content'],
            source=row['source'],
            source_type=SourceType(row['source_type']),
            embedding_model=row['embedding_model'],
            embedding_model_key=row['embedding_model_key'] if 'embedding_model_key' in row else None,
            embedding_dimension=row['embedding_dimension'] if 'embedding_dimension' in row else None,
            indexed=row['indexed'],
            indexed_at=row['indexed_at'],
            index_status=(row['index_status'] if 'index_status' in row and row['index_status'] else ('ready' if row['indexed'] else 'pending')),
            index_version=int(row['index_version']) if 'index_version' in row and row['index_version'] is not None else 1,
            last_index_error=row['last_index_error'] if 'last_index_error' in row else None,
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            metadata=metadata,
        )

    def _row_to_index_job(self, row: asyncpg.Record) -> Dict[str, Any]:
        payload = row["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)

        return {
            "id": str(row["id"]),
            "tenant_id": str(row["tenant_id"]),
            "knowledge_base_id": str(row["knowledge_base_id"]) if row["knowledge_base_id"] else None,
            "document_id": str(row["document_id"]),
            "job_type": row["job_type"],
            "target_version": int(row["target_version"]) if row["target_version"] is not None else None,
            "status": row["status"],
            "attempts": int(row["attempts"]),
            "next_run_at": row["next_run_at"],
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
            "last_error": row["last_error"],
            "payload": payload or {},
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
