"""
Document Service - Business Logic Layer
"""
import logging
from typing import List, Optional, Dict, Any
from fastapi import UploadFile

from core.models.knowledge_base import (
    Document,
    SourceType,
    AccessLevel,
    CreateDocumentRequest,
    UpdateDocumentRequest,
)
from core.repositories.document_repository import DocumentRepository
from core.repositories.knowledge_base_repository import KnowledgeBaseRepository
from core.embeddings import EmbeddingService
from core.parsers.file_parser import FileParser
from core.parsers.url_fetcher import URLFetcher
from core.audit import AuditLogger
from core.quota import QuotaManager


logger = logging.getLogger(__name__)


class DocumentService:
    """文档业务逻辑服务"""

    def __init__(
        self,
        repository: DocumentRepository,
        kb_repository: KnowledgeBaseRepository,
        embedding_service: EmbeddingService,
        audit_logger: Optional[AuditLogger] = None,
        quota_manager: Optional[QuotaManager] = None,
    ):
        """
        初始化服务

        Args:
            repository: 文档数据库仓库
            kb_repository: 知识库数据库仓库
            embedding_service: 向量嵌入服务
            audit_logger: 审计日志服务（可选）
            quota_manager: 配额管理服务（可选）
        """
        self.repository = repository
        self.kb_repository = kb_repository
        self.embedding_service = embedding_service
        self.audit_logger = audit_logger
        self.quota_manager = quota_manager
        self.url_fetcher = URLFetcher()

    async def create_document(
        self,
        tenant_id: str,
        user_id: Optional[str],
        request: CreateDocumentRequest,
        context: Optional[Dict[str, Any]] = None,
    ) -> Document:
        """
        创建文档

        Args:
            tenant_id: 租户ID
            user_id: 用户ID
            request: 创建请求
            context: 请求上下文（用于审计日志）

        Returns:
            创建的文档对象
        """
        # 验证知识库存在且用户有权限访问
        kb = await self.kb_repository.get_knowledge_base(
            kb_id=request.knowledge_base_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        if not kb:
            raise ValueError(f"Knowledge base {request.knowledge_base_id} not found or access denied")

        # 检查配额
        if self.quota_manager:
            await self.quota_manager.check_document_quota(tenant_id)
            await self.quota_manager.check_document_size(request.content)

        # 生成向量嵌入
        embedding = None
        embedding_model = None

        if request.auto_index:
            try:
                embedding = await self.embedding_service.embed_text(request.content)
                embedding_model = self.embedding_service.get_model_name()
            except Exception as e:
                logger.error(f"Failed to generate embedding: {e}")
                # 继续创建文档，但标记为未索引

        # 创建文档
        doc = await self.repository.create_document(
            tenant_id=tenant_id,
            user_id=user_id if request.access_level == AccessLevel.USER else None,
            knowledge_base_id=request.knowledge_base_id,
            access_level=request.access_level,
            title=request.title,
            content=request.content,
            source=request.source,
            source_type=request.source_type,
            embedding=embedding,
            embedding_model=embedding_model,
            metadata=request.metadata,
        )

        # 审计日志
        if self.audit_logger:
            await self.audit_logger.log_document_create(
                document_id=doc.id,
                tenant_id=tenant_id,
                user_id=user_id,
                title=request.title,
                source_type=request.source_type.value,
                ip_address=context.get("ip_address") if context else None,
                user_agent=context.get("user_agent") if context else None,
            )

        # 更新配额追踪
        if self.quota_manager:
            await self.quota_manager.update_quota_tracking(tenant_id)

        return doc

    async def get_document(
        self,
        document_id: str,
        tenant_id: str,
        user_id: Optional[str],
    ) -> Optional[Document]:
        """获取文档"""
        return await self.repository.get_document(document_id, tenant_id, user_id)

    async def update_document(
        self,
        document_id: str,
        tenant_id: str,
        user_id: Optional[str],
        request: UpdateDocumentRequest,
    ) -> Optional[Document]:
        """
        更新文档

        Args:
            document_id: 文档ID
            tenant_id: 租户ID
            user_id: 用户ID
            request: 更新请求

        Returns:
            更新后的文档，如果不存在或无权限则返回None
        """
        # 如果内容更新且需要重新索引
        embedding = None
        embedding_model = None

        if request.re_index and request.content:
            try:
                embedding = await self.embedding_service.embed_text(request.content)
                embedding_model = self.embedding_service.get_model_name()
            except Exception as e:
                logger.error(f"Failed to generate embedding: {e}")

        return await self.repository.update_document(
            document_id=document_id,
            tenant_id=tenant_id,
            user_id=user_id,
            title=request.title,
            content=request.content,
            source=request.source,
            metadata=request.metadata,
            embedding=embedding,
            embedding_model=embedding_model,
        )

    async def delete_document(
        self,
        document_id: str,
        tenant_id: str,
        user_id: Optional[str],
    ) -> bool:
        """删除文档"""
        return await self.repository.delete_document(document_id, tenant_id, user_id)

    async def list_documents(
        self,
        tenant_id: str,
        user_id: Optional[str],
        access_level: Optional[AccessLevel] = None,
        source_type: Optional[SourceType] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[List[Document], int]:
        """列出文档（分页）"""
        return await self.repository.list_documents(
            tenant_id=tenant_id,
            user_id=user_id,
            access_level=access_level,
            source_type=source_type,
            page=page,
            page_size=page_size,
        )

    async def search_documents(
        self,
        tenant_id: str,
        user_id: Optional[str],
        query: str,
        top_k: int = 5,
        access_level: Optional[AccessLevel] = None,
        source_type: Optional[SourceType] = None,
    ) -> List[tuple[Document, float]]:
        """
        搜索文档

        Args:
            tenant_id: 租户ID
            user_id: 用户ID
            query: 搜索查询
            top_k: 返回结果数量
            access_level: 筛选访问级别
            source_type: 筛选来源类型

        Returns:
            [(文档, 相似度分数), ...]
        """
        # 生成查询向量
        query_embedding = await self.embedding_service.embed_text(query)

        # 向量搜索
        return await self.repository.search_by_embedding(
            tenant_id=tenant_id,
            query_embedding=query_embedding,
            user_id=user_id,
            top_k=top_k,
            access_level=access_level,
            source_type=source_type,
        )

    async def upload_file(
        self,
        tenant_id: str,
        user_id: Optional[str],
        file: UploadFile,
        access_level: AccessLevel = AccessLevel.TENANT,
        auto_index: bool = True,
    ) -> Document:
        """
        上传文件并创建文档

        Args:
            tenant_id: 租户ID
            user_id: 用户ID
            file: 上传的文件
            access_level: 访问级别
            auto_index: 是否自动索引

        Returns:
            创建的文档对象

        Raises:
            ValueError: 文件类型不支持或解析失败
        """
        # 检查文件类型
        if not FileParser.is_supported(file.filename):
            raise ValueError(
                f"Unsupported file type: {file.filename}. "
                f"Supported: .txt, .md, .pdf, .html, .htm"
            )

        # 读取文件内容
        file_content = await file.read()

        # 解析文件
        parser = FileParser.get_parser(file.filename)
        parsed_content = await parser.parse(file_content, file.filename)

        if not parsed_content.strip():
            raise ValueError("File content is empty after parsing")

        # 使用文件名作为标题（去除扩展名）
        import os
        title = os.path.splitext(file.filename)[0]

        # 创建文档
        request = CreateDocumentRequest(
            title=title,
            content=parsed_content,
            source=file.filename,
            source_type=SourceType.FILE,
            access_level=access_level,
            auto_index=auto_index,
            metadata={
                "file_size": len(file_content),
                "file_type": file.content_type,
            }
        )

        return await self.create_document(tenant_id, user_id, request)

    async def create_from_url(
        self,
        tenant_id: str,
        user_id: Optional[str],
        url: str,
        access_level: AccessLevel = AccessLevel.TENANT,
        auto_index: bool = True,
    ) -> Document:
        """
        从URL抓取内容并创建文档

        Args:
            tenant_id: 租户ID
            user_id: 用户ID
            url: 目标URL
            access_level: 访问级别
            auto_index: 是否自动索引

        Returns:
            创建的文档对象

        Raises:
            ValueError: URL抓取失败
        """
        # 抓取URL内容
        content, title = await self.url_fetcher.fetch_text(url)

        if not content.strip():
            raise ValueError("No content extracted from URL")

        # 创建文档
        request = CreateDocumentRequest(
            title=title,
            content=content,
            source=url,
            source_type=SourceType.URL,
            access_level=access_level,
            auto_index=auto_index,
            metadata={"url": url}
        )

        return await self.create_document(tenant_id, user_id, request)

    async def batch_create_documents(
        self,
        tenant_id: str,
        user_id: Optional[str],
        requests: List[CreateDocumentRequest],
    ) -> List[Dict[str, Any]]:
        """
        批量创建文档

        Args:
            tenant_id: 租户ID
            user_id: 用户ID
            requests: 创建请求列表

        Returns:
            结果列表，每项包含：{"index": int, "success": bool, "id": str, "error": str}
        """
        results = []

        for idx, request in enumerate(requests):
            try:
                doc = await self.create_document(tenant_id, user_id, request)
                results.append({
                    "index": idx,
                    "success": True,
                    "id": doc.id,
                    "error": None,
                })
            except Exception as e:
                logger.error(f"Failed to create document at index {idx}: {e}")
                results.append({
                    "index": idx,
                    "success": False,
                    "id": None,
                    "error": str(e),
                })

        return results
