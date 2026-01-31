"""
Knowledge Base Repository - Database Access Layer
"""
import json
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
import asyncpg
from ..models.knowledge_base import (
    Document,
    SourceType,
    AccessLevel,
)


class KnowledgeBaseRepository:
    """知识库数据库访问层"""

    def __init__(self, db_pool: asyncpg.Pool, use_pgvector: bool = False):
        """
        初始化仓库

        Args:
            db_pool: asyncpg 连接池
            use_pgvector: 是否使用pgvector扩展（需要数据库安装pgvector）
        """
        self.db_pool = db_pool
        self.use_pgvector = use_pgvector

    async def create_document(
        self,
        tenant_id: str,
        title: str,
        content: str,
        user_id: Optional[str] = None,
        access_level: AccessLevel = AccessLevel.TENANT,
        source: Optional[str] = None,
        source_type: SourceType = SourceType.MANUAL,
        embedding_model: Optional[str] = None,
        embedding: Optional[List[float]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Document:
        """
        创建文档

        Args:
            tenant_id: 租户ID
            title: 文档标题
            content: 文档内容
            user_id: 用户ID（私有文档）
            access_level: 访问级别
            source: 来源
            source_type: 来源类型
            embedding_model: 嵌入模型名称
            embedding: 向量嵌入
            metadata: 额外元数据

        Returns:
            创建的文档对象
        """
        doc_id = str(uuid.uuid4())
        indexed = embedding is not None
        indexed_at = datetime.utcnow() if indexed else None
        now = datetime.utcnow()

        query = """
            INSERT INTO documents (
                id, tenant_id, user_id, access_level, title, content,
                source, source_type, embedding_model, embedding,
                indexed, indexed_at, created_at, updated_at, metadata
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
            RETURNING *
        """

        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                doc_id,
                tenant_id,
                user_id,
                access_level.value,
                title,
                content,
                source,
                source_type.value,
                embedding_model,
                embedding,  # PostgreSQL 支持存储数组
                indexed,
                indexed_at,
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
        embedding: Optional[List[float]] = None,
        embedding_model: Optional[str] = None,
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
            embedding: 新向量
            embedding_model: 嵌入模型

        Returns:
            更新后的文档，如果不存在或无权限则返回None
        """
        # 构建动态更新字段
        updates = ["updated_at = $1"]
        params = [datetime.utcnow()]
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

        if embedding is not None:
            updates.append(f"embedding = ${param_idx}")
            params.append(embedding)
            param_idx += 1

            updates.append(f"indexed = ${param_idx}")
            params.append(True)
            param_idx += 1

            updates.append(f"indexed_at = ${param_idx}")
            params.append(datetime.utcnow())
            param_idx += 1

            if embedding_model:
                updates.append(f"embedding_model = ${param_idx}")
                params.append(embedding_model)
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

        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(query, *params)

        return self._row_to_document(row) if row else None

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

    async def search_by_embedding(
        self,
        tenant_id: str,
        query_embedding: List[float],
        user_id: Optional[str] = None,
        top_k: int = 5,
        access_level: Optional[AccessLevel] = None,
        source_type: Optional[SourceType] = None,
    ) -> List[tuple[Document, float]]:
        """
        基于向量相似度搜索文档

        Args:
            tenant_id: 租户ID
            query_embedding: 查询向量
            user_id: 用户ID
            top_k: 返回结果数量
            access_level: 筛选访问级别
            source_type: 筛选来源类型

        Returns:
            [(文档, 相似度分数), ...]，按分数降序排列
        """
        conditions = ["tenant_id = $1", "indexed = true", "embedding IS NOT NULL"]
        params = [tenant_id]
        param_idx = 2

        # 权限过滤
        if access_level:
            conditions.append(f"access_level = ${param_idx}")
            params.append(access_level.value)
            param_idx += 1
        else:
            conditions.append(f"(access_level = 'tenant' OR (access_level = 'user' AND user_id = ${param_idx}))")
            params.append(user_id)
            param_idx += 1

        # 来源类型过滤
        if source_type:
            conditions.append(f"source_type = ${param_idx}")
            params.append(source_type.value)
            param_idx += 1

        where_clause = " AND ".join(conditions)

        # 根据是否使用pgvector选择不同的查询方法
        if self.use_pgvector:
            # 使用 pgvector 的余弦距离操作符（更快）
            # 余弦距离 = 1 - 余弦相似度
            query = f"""
                SELECT *,
                    1 - (embedding <=> ${param_idx}::vector) AS similarity
                FROM documents
                WHERE {where_clause}
                ORDER BY embedding <=> ${param_idx}::vector
                LIMIT ${param_idx + 1}
            """
        else:
            # 使用原生数组计算余弦相似度（兼容模式）
            # 使用点积和范数计算
            query = f"""
                SELECT *,
                    (
                        (
                            SELECT SUM(a * b)
                            FROM unnest(embedding, ${param_idx}::float[]) AS t(a, b)
                        ) /
                        (
                            sqrt((SELECT SUM(a * a) FROM unnest(embedding) AS t(a))) *
                            sqrt((SELECT SUM(b * b) FROM unnest(${param_idx}::float[]) AS t(b)))
                        )
                    ) AS similarity
                FROM documents
                WHERE {where_clause}
                ORDER BY similarity DESC NULLS LAST
                LIMIT ${param_idx + 1}
            """

        params.extend([query_embedding, top_k])

        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        results = []
        for row in rows:
            doc = self._row_to_document(row)
            score = float(row['similarity']) if row['similarity'] is not None else 0.0

            # pgvector返回的已经是[0,1]范围，原生计算也是[-1,1]需要归一化
            if not self.use_pgvector and score < 0:
                # 归一化到 [0, 1]
                score = (score + 1) / 2

            results.append((doc, score))

        return results

    def _row_to_document(self, row) -> Document:
        """将数据库行转换为Document对象"""
        metadata = row['metadata']
        if isinstance(metadata, str):
            metadata = json.loads(metadata)

        return Document(
            id=str(row['id']),
            tenant_id=str(row['tenant_id']),
            user_id=str(row['user_id']) if row['user_id'] else None,
            access_level=AccessLevel(row['access_level']),
            title=row['title'],
            content=row['content'],
            source=row['source'],
            source_type=SourceType(row['source_type']),
            embedding_model=row['embedding_model'],
            indexed=row['indexed'],
            indexed_at=row['indexed_at'],
            created_at=row['created_at'],
            updated_at=row['updated_at'],
            metadata=metadata,
            embedding=list(row['embedding']) if row['embedding'] else None,
        )
