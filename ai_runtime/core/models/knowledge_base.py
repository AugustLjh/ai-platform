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
    skip_duplicate_check: bool = Field(False, description="是否跳过重复/相似文档检测")


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


# Knowledge Base Settings Schemas
class IndexingSettings(BaseModel):
    """知识库索引设置"""
    indexing_method: str = Field(default="chunk", description="Indexing method: chunk/full")
    chunk_size: int = Field(default=500, ge=50, le=2000)
    chunk_overlap: int = Field(default=50, ge=0, le=500)
    embedding_model_id: Optional[str] = None


class IndexingSettingsUpdate(BaseModel):
    """更新索引设置"""
    indexing_method: Optional[str] = None
    chunk_size: Optional[int] = Field(default=None, ge=50, le=2000)
    chunk_overlap: Optional[int] = Field(default=None, ge=0, le=500)
    embedding_model_id: Optional[str] = None


class RetrievalSettings(BaseModel):
    """知识库检索设置"""
    retrieval_method: str = Field(default="vector", description="Retrieval method: vector/keyword/hybrid")
    top_k: int = Field(default=5, ge=1, le=50)
    score_threshold: float = Field(default=0.0, ge=0.0, le=1.0)
    enable_rerank: bool = Field(default=False)
    rerank_model_id: Optional[str] = None


class RetrievalSettingsUpdate(BaseModel):
    """更新检索设置"""
    retrieval_method: Optional[str] = None
    top_k: Optional[int] = Field(default=None, ge=1, le=50)
    score_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    enable_rerank: Optional[bool] = None
    rerank_model_id: Optional[str] = None


class GovernanceRouteSettings(BaseModel):
    """单个场景的模型路由配置"""
    enabled: bool = Field(default=True)
    primary_model_id: Optional[str] = None
    fallback_model_id: Optional[str] = None


class GovernanceRouteSettingsUpdate(BaseModel):
    """更新单个场景的模型路由配置"""
    enabled: Optional[bool] = None
    primary_model_id: Optional[str] = None
    fallback_model_id: Optional[str] = None


class AIGovernanceSettings(BaseModel):
    """知识库级 AI 运营与治理配置"""
    config_version: int = Field(default=1, ge=1)
    budget_alert_usd: Optional[float] = Field(default=None, ge=0.0)
    low_quality_threshold: float = Field(default=2.0, ge=0.0, le=5.0)
    routes: Dict[str, GovernanceRouteSettings] = Field(default_factory=dict)


class AIGovernanceSettingsUpdate(BaseModel):
    """更新知识库级 AI 运营与治理配置"""
    budget_alert_usd: Optional[float] = Field(default=None, ge=0.0)
    low_quality_threshold: Optional[float] = Field(default=None, ge=0.0, le=5.0)
    routes: Optional[Dict[str, GovernanceRouteSettingsUpdate]] = None


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
    knowledge_base_id: Optional[str] = Field(None, description="知识库ID（可选）")
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


class DocumentPreviewResponse(BaseModel):
    """文档预览响应"""
    document_id: str
    title: str
    source: Optional[str]
    total_chars: int
    preview_chars: int
    truncated: bool
    preview: str
    indexed: bool
    indexed_at: Optional[str]
    updated_at: str


class DocumentSegment(BaseModel):
    """文档分段信息"""
    segment_index: int = Field(..., ge=1)
    start_offset: int = Field(..., ge=0)
    end_offset: int = Field(..., ge=0)
    char_count: int = Field(..., ge=0)
    content: str
    match_score: Optional[float] = None


class DocumentSegmentsResponse(BaseModel):
    """文档分段详情响应"""
    document_id: str
    title: str
    chunk_size: int
    chunk_overlap: int
    total_segments: int
    returned_segments: int
    truncated: bool
    segments: List[DocumentSegment]


class RetrievalTestRequest(BaseModel):
    """召回测试请求"""
    query: str = Field(..., min_length=1, description="测试查询")
    top_k: Optional[int] = Field(None, ge=1, le=50, description="可选覆盖 Top K")
    score_threshold: Optional[float] = Field(None, ge=0.0, le=1.0, description="可选覆盖阈值")


class RetrievalTestResult(BaseModel):
    """召回测试结果项"""
    document: DocumentResponse
    score: float = Field(..., ge=0, le=1)
    matched_segments: List[DocumentSegment] = Field(default_factory=list)


class RetrievalTestResponse(BaseModel):
    """召回测试响应"""
    query: str
    retrieval_method: str
    top_k: int
    score_threshold: float
    total: int
    results: List[RetrievalTestResult]


class RetrievalEvaluationCase(BaseModel):
    """评测样本"""
    id: Optional[str] = None
    query: str = Field(..., min_length=1, description="测试问题")
    expected_document_ids: List[str] = Field(default_factory=list, description="期望命中文档 ID 列表")
    expected_documents: List[Dict[str, Any]] = Field(default_factory=list, description="期望文档摘要")
    notes: Optional[str] = Field(None, description="样本备注")


class RetrievalTestSetCreateRequest(BaseModel):
    """创建检索测试集"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    cases: List[RetrievalEvaluationCase] = Field(..., min_items=1, max_items=200)


class RetrievalTestSetUpdateRequest(BaseModel):
    """更新检索测试集"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    cases: List[RetrievalEvaluationCase] = Field(..., min_items=1, max_items=200)


class RetrievalTestSetResponse(BaseModel):
    """检索测试集响应"""
    id: str
    tenant_id: str
    knowledge_base_id: str
    user_id: Optional[str]
    name: str
    description: Optional[str]
    cases: List[RetrievalEvaluationCase]
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class RetrievalEvaluationConfig(BaseModel):
    """评测时使用的检索配置"""
    retrieval_method: Optional[str] = None
    top_k: Optional[int] = Field(default=None, ge=1, le=50)
    score_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    enable_rerank: Optional[bool] = None
    rerank_model_id: Optional[str] = None


class RetrievalEvaluationRunRequest(BaseModel):
    """发起评测运行"""
    test_set_id: str
    name: Optional[str] = Field(None, max_length=255)
    config: RetrievalEvaluationConfig = Field(default_factory=RetrievalEvaluationConfig)


class RetrievalEvaluationResultItem(BaseModel):
    """单条样本评测结果"""
    case_id: str
    query: str
    notes: Optional[str] = None
    expected_document_ids: List[str] = Field(default_factory=list)
    expected_documents: List[Dict[str, Any]] = Field(default_factory=list)
    matched_document_ids: List[str] = Field(default_factory=list)
    top_result_document_id: Optional[str] = None
    hit: bool
    top_hit: bool
    manual_score: Optional[float] = Field(default=None, ge=0.0, le=5.0)
    manual_comment: Optional[str] = None
    results: List[Dict[str, Any]] = Field(default_factory=list)


class RetrievalEvaluationSummary(BaseModel):
    """评测汇总"""
    total_cases: int
    hit_count: int
    top_hit_count: int
    hit_rate: float
    top_hit_rate: float
    avg_manual_score: Optional[float] = None
    manual_score_count: int = 0


class RetrievalEvaluationRunResponse(BaseModel):
    """评测运行响应"""
    id: str
    tenant_id: str
    knowledge_base_id: str
    test_set_id: Optional[str]
    user_id: Optional[str]
    name: Optional[str]
    config: Dict[str, Any] = Field(default_factory=dict)
    summary: RetrievalEvaluationSummary
    results: List[RetrievalEvaluationResultItem] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class RetrievalEvaluationFeedbackRequest(BaseModel):
    """更新人工评分"""
    case_id: str
    manual_score: Optional[float] = Field(default=None, ge=0.0, le=5.0)
    manual_comment: Optional[str] = None


class RetrievalEvaluationApplyConfigResponse(BaseModel):
    """应用评测配置响应"""
    retrieval_settings: RetrievalSettings
    run_id: str
