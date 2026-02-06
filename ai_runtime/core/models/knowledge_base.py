"""
Knowledge Base Data Models and Schemas
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class SourceType(str, Enum):
    """文档来源类型"""
    FILE = "file"
    URL = "url"
    MANUAL = "manual"
    BATCH = "batch"


class AccessLevel(str, Enum):
    """访问权限级别"""
    TENANT = "tenant"  # 租户级别（公共）
    USER = "user"      # 用户级别（私有）


# === 数据库模型 ===

class KnowledgeBase:
    """知识库数据库模型"""
    def __init__(
        self,
        id: str,
        tenant_id: str,
        name: str,
        description: Optional[str] = None,
        user_id: Optional[str] = None,
        access_level: AccessLevel = AccessLevel.TENANT,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.id = id
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.name = name
        self.description = description
        self.access_level = access_level
        self.created_at = created_at or datetime.utcnow()
        self.updated_at = updated_at or datetime.utcnow()
        self.metadata = metadata or {}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "name": self.name,
            "description": self.description,
            "access_level": self.access_level.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
        }


class Document:
    """文档数据库模型"""
    def __init__(
        self,
        id: str,
        tenant_id: str,
        title: str,
        content: str,
        knowledge_base_id: Optional[str] = None,
        source: Optional[str] = None,
        source_type: SourceType = SourceType.MANUAL,
        embedding_model: Optional[str] = None,
        indexed: bool = False,
        indexed_at: Optional[datetime] = None,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,  # 添加用户ID用于混合权限模式
        access_level: AccessLevel = AccessLevel.TENANT,
        embedding: Optional[List[float]] = None,
    ):
        self.id = id
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.knowledge_base_id = knowledge_base_id
        self.access_level = access_level
        self.title = title
        self.content = content
        self.source = source
        self.source_type = source_type
        self.embedding_model = embedding_model
        self.indexed = indexed
        self.indexed_at = indexed_at
        self.created_at = created_at or datetime.utcnow()
        self.updated_at = updated_at or datetime.utcnow()
        self.metadata = metadata or {}
        self.embedding = embedding

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "knowledge_base_id": self.knowledge_base_id,
            "access_level": self.access_level.value,
            "title": self.title,
            "content": self.content,
            "source": self.source,
            "source_type": self.source_type.value,
            "embedding_model": self.embedding_model,
            "indexed": self.indexed,
            "indexed_at": self.indexed_at.isoformat() if self.indexed_at else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
        }


# === API Request/Response Schemas ===

# Knowledge Base Schemas
class CreateKnowledgeBaseRequest(BaseModel):
    """创建知识库请求"""
    name: str = Field(..., min_length=1, max_length=255, description="知识库名称")
    description: Optional[str] = Field(None, description="知识库描述")
    access_level: AccessLevel = Field(AccessLevel.TENANT, description="访问权限")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="额外元数据")


class UpdateKnowledgeBaseRequest(BaseModel):
    """更新知识库请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=255, description="知识库名称")
    description: Optional[str] = Field(None, description="知识库描述")
    metadata: Optional[Dict[str, Any]] = None


class KnowledgeBaseResponse(BaseModel):
    """知识库响应"""
    id: str
    tenant_id: str
    user_id: Optional[str]
    name: str
    description: Optional[str]
    access_level: str
    created_at: str
    updated_at: str
    metadata: Dict[str, Any]


class KnowledgeBaseWithStats(BaseModel):
    """带统计信息的知识库响应"""
    id: str
    tenant_id: str
    user_id: Optional[str]
    name: str
    description: Optional[str]
    access_level: str
    created_at: str
    updated_at: str
    metadata: Dict[str, Any]
    document_count: int = Field(0, description="文档数量")


class ListKnowledgeBasesResponse(BaseModel):
    """知识库列表响应"""
    knowledge_bases: List[KnowledgeBaseWithStats]
    total: int
    page: int
    page_size: int


# Document Schemas
class CreateDocumentRequest(BaseModel):
    """创建文档请求"""
    knowledge_base_id: str = Field(..., description="所属知识库ID")
    title: str = Field(..., min_length=1, max_length=255, description="文档标题")
    content: str = Field(..., min_length=1, description="文档内容")
    source: Optional[str] = Field(None, max_length=255, description="来源URL或文件名")
    source_type: SourceType = Field(SourceType.MANUAL, description="来源类型")
    access_level: AccessLevel = Field(AccessLevel.TENANT, description="访问权限")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="额外元数据")
    auto_index: bool = Field(True, description="是否自动生成向量索引")


class UpdateDocumentRequest(BaseModel):
    """更新文档请求"""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    content: Optional[str] = Field(None, min_length=1)
    source: Optional[str] = Field(None, max_length=255)
    metadata: Optional[Dict[str, Any]] = None
    re_index: bool = Field(False, description="是否重新生成索引")


class DocumentResponse(BaseModel):
    """文档响应"""
    id: str
    tenant_id: str
    user_id: Optional[str]
    knowledge_base_id: Optional[str]
    access_level: str
    title: str
    content: str
    source: Optional[str]
    source_type: str
    embedding_model: Optional[str]
    indexed: bool
    indexed_at: Optional[str]
    created_at: str
    updated_at: str
    metadata: Dict[str, Any]


class ListDocumentsResponse(BaseModel):
    """文档列表响应"""
    documents: List[DocumentResponse]
    total: int
    page: int
    page_size: int


class BatchCreateRequest(BaseModel):
    """批量创建文档请求"""
    documents: List[CreateDocumentRequest] = Field(..., max_items=100)


class BatchCreateResponse(BaseModel):
    """批量创建响应"""
    success_count: int
    failed_count: int
    results: List[Dict[str, Any]]  # {"index": 0, "success": True, "id": "xxx", "error": None}


class SearchDocumentsRequest(BaseModel):
    """搜索文档请求"""
    query: str = Field(..., min_length=1, description="搜索查询")
    top_k: int = Field(5, ge=1, le=50, description="返回结果数量")
    access_level: Optional[AccessLevel] = Field(None, description="筛选访问权限")
    source_type: Optional[SourceType] = Field(None, description="筛选来源类型")


class SearchResult(BaseModel):
    """搜索结果项"""
    document: DocumentResponse
    score: float = Field(..., ge=0, le=1, description="相关度分数")


class SearchDocumentsResponse(BaseModel):
    """搜索响应"""
    results: List[SearchResult]
    query: str
    total: int


class FileUploadResponse(BaseModel):
    """文件上传响应"""
    document_id: str
    filename: str
    file_type: str
    content_length: int
    indexed: bool
