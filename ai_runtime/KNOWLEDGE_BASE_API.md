# 知识库管理API文档

## 概述

ai_runtime服务现已支持完整的知识库增删改查接口，包括：
- 文档管理（CRUD操作）
- 文件上传（TXT, PDF, Markdown, HTML）
- URL内容抓取
- 批量导入
- 向量语义搜索

## 技术栈

- **向量嵌入**: sentence-transformers (本地多语言模型)
- **数据库**: PostgreSQL (asyncpg)
- **文件解析**: PyPDF2, BeautifulSoup4
- **权限模型**: 租户级（公共）+ 用户级（私有）

## API端点

所有端点前缀：`/api/v1/knowledge`

### 1. 创建文档

**POST** `/documents`

手动创建文档，自动生成向量索引。

```json
{
  "title": "API使用指南",
  "content": "这是文档的完整内容...",
  "source": "manual input",
  "source_type": "manual",
  "access_level": "tenant",
  "auto_index": true,
  "metadata": {
    "author": "张三",
    "category": "技术文档"
  }
}
```

**响应**: `DocumentResponse` (201 Created)

### 2. 获取文档

**GET** `/documents/{document_id}`

获取单个文档详情。

**响应**: `DocumentResponse`

### 3. 更新文档

**PUT** `/documents/{document_id}`

更新文档内容或元数据。

```json
{
  "title": "新标题",
  "content": "更新后的内容",
  "re_index": true
}
```

**响应**: `DocumentResponse`

### 4. 删除文档

**DELETE** `/documents/{document_id}`

删除文档。

**响应**: 204 No Content

### 5. 列出文档

**GET** `/documents?page=1&page_size=20&access_level=tenant&source_type=file`

分页列出文档。

**查询参数**:
- `page`: 页码（默认1）
- `page_size`: 每页数量（1-100，默认20）
- `access_level`: 筛选访问级别（tenant/user）
- `source_type`: 筛选来源类型（file/url/manual/batch）

**响应**: `ListDocumentsResponse`

### 6. 向量语义搜索

**POST** `/documents/search`

基于语义相似度搜索文档。

```json
{
  "query": "如何使用API进行文件上传",
  "top_k": 5,
  "access_level": null,
  "source_type": null
}
```

**响应**: `SearchDocumentsResponse`

```json
{
  "results": [
    {
      "document": { ... },
      "score": 0.85
    }
  ],
  "query": "如何使用API进行文件上传",
  "total": 3
}
```

### 7. 文件上传

**POST** `/documents/upload`

上传文件并自动解析内容。

**表单数据**:
- `file`: 文件（multipart/form-data）
- `access_level`: 访问权限（默认tenant）
- `auto_index`: 是否自动索引（默认true）

**支持格式**: .txt, .md, .pdf, .html, .htm

**响应**: `DocumentResponse` (201 Created)

### 8. 从URL创建

**POST** `/documents/from-url`

从URL抓取内容并创建文档。

**表单数据**:
- `url`: 目标URL
- `access_level`: 访问权限（默认tenant）
- `auto_index`: 是否自动索引（默认true）

**响应**: `DocumentResponse` (201 Created)

### 9. 批量创建

**POST** `/documents/batch`

批量创建文档（最多100个）。

```json
{
  "documents": [
    {
      "title": "文档1",
      "content": "内容1",
      ...
    },
    {
      "title": "文档2",
      "content": "内容2",
      ...
    }
  ]
}
```

**响应**: `BatchCreateResponse`

```json
{
  "success_count": 95,
  "failed_count": 5,
  "results": [
    {
      "index": 0,
      "success": true,
      "id": "uuid",
      "error": null
    },
    ...
  ]
}
```

### 10. 统计信息

**GET** `/stats`

获取知识库统计数据。

**响应**:
```json
{
  "total_documents": 150,
  "indexed_documents": 145,
  "unindexed_documents": 5,
  "by_source_type": {
    "file": 80,
    "url": 40,
    "manual": 30
  },
  "by_access_level": {
    "tenant": 120,
    "user": 30
  }
}
```

## 数据模型

### DocumentResponse

```typescript
{
  id: string
  tenant_id: string
  user_id: string | null
  access_level: "tenant" | "user"
  title: string
  content: string
  source: string | null
  source_type: "file" | "url" | "manual" | "batch"
  embedding_model: string | null
  indexed: boolean
  indexed_at: string | null
  created_at: string
  updated_at: string
  metadata: object
}
```

## 权限模型

### 混合模式（租户级 + 用户级）

- **tenant级文档**: 同一租户下所有用户可见
- **user级文档**: 仅创建用户本人可见

查询时自动过滤：
- 用户可以看到所有tenant级文档
- 用户只能看到自己创建的user级文档

## 使用示例

### Python 客户端

```python
import requests

BASE_URL = "http://localhost:8000/api/v1/knowledge"

# 1. 创建文档
response = requests.post(f"{BASE_URL}/documents", json={
    "title": "快速开始指南",
    "content": "本指南介绍如何快速开始使用...",
    "access_level": "tenant",
    "auto_index": True
})
doc = response.json()
print(f"文档已创建: {doc['id']}")

# 2. 上传文件
with open("document.pdf", "rb") as f:
    files = {"file": f}
    data = {"access_level": "tenant", "auto_index": "true"}
    response = requests.post(f"{BASE_URL}/documents/upload", files=files, data=data)
    print(f"文件已上传: {response.json()['id']}")

# 3. 从URL创建
response = requests.post(f"{BASE_URL}/documents/from-url", data={
    "url": "https://example.com/docs/api",
    "access_level": "tenant"
})
print(f"从URL创建: {response.json()['id']}")

# 4. 语义搜索
response = requests.post(f"{BASE_URL}/documents/search", json={
    "query": "如何上传文件",
    "top_k": 5
})
results = response.json()
for item in results['results']:
    print(f"- {item['document']['title']} (分数: {item['score']})")

# 5. 列出所有文档
response = requests.get(f"{BASE_URL}/documents?page=1&page_size=20")
docs = response.json()
print(f"共找到 {docs['total']} 个文档")

# 6. 更新文档
response = requests.put(f"{BASE_URL}/documents/{doc['id']}", json={
    "title": "快速开始指南 v2",
    "re_index": True
})

# 7. 删除文档
response = requests.delete(f"{BASE_URL}/documents/{doc['id']}")
```

### cURL 示例

```bash
# 创建文档
curl -X POST http://localhost:8000/api/v1/knowledge/documents \
  -H "Content-Type: application/json" \
  -d '{
    "title": "测试文档",
    "content": "这是测试内容",
    "access_level": "tenant"
  }'

# 上传文件
curl -X POST http://localhost:8000/api/v1/knowledge/documents/upload \
  -F "file=@document.pdf" \
  -F "access_level=tenant"

# 搜索
curl -X POST http://localhost:8000/api/v1/knowledge/documents/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "搜索关键词",
    "top_k": 5
  }'

# 列出文档
curl http://localhost:8000/api/v1/knowledge/documents?page=1&page_size=20

# 获取统计
curl http://localhost:8000/api/v1/knowledge/stats
```

## 与RAG系统集成

知识库已集成到现有RAG管道，支持两种向量存储：

### 1. 简单内存存储（原有，用于测试）

```python
from ai_runtime.core.rag.retriever import SimpleVectorStore, Retriever

vector_store = SimpleVectorStore()
retriever = Retriever(vector_store)
```

### 2. 数据库向量存储（新增，生产推荐）

```python
from ai_runtime.core.rag.retriever import DatabaseVectorStore, Retriever
from ai_runtime.core.services.knowledge_base import KnowledgeBaseService

# 初始化知识库服务
kb_service = KnowledgeBaseService(repository, embedding_service)

# 创建数据库向量存储
vector_store = DatabaseVectorStore(
    kb_service=kb_service,
    tenant_id="your-tenant-id",
    user_id="your-user-id"
)

# 使用检索器
retriever = Retriever(vector_store)
docs = await retriever.retrieve("查询内容", top_k=5)
```

## 部署配置

### 1. 数据库迁移

运行数据库迁移以添加新字段：

```bash
# 应用迁移
psql -U postgres -d ai_platform < db/migrations/001_initial_schema.sql
psql -U postgres -d ai_platform < db/migrations/002_knowledge_base_enhancements.sql
psql -U postgres -d ai_platform < db/migrations/004_add_knowledge_bases.sql
psql -U postgres -d ai_platform < db/migrations/005_migrate_existing_documents.sql
# 可选：pgvector优化（需要先安装pgvector扩展）
# psql -U postgres -d ai_platform < db/migrations/003_enable_pgvector.sql
```

### 2. 安装依赖

```bash
cd ai_runtime
pip install -r requirements.txt
```

首次运行时，sentence-transformers会自动下载模型（约120MB）：
- 模型：`paraphrase-multilingual-MiniLM-L12-v2`
- 支持中英文等多语言
- 向量维度：384

### 3. 配置依赖注入

在主应用中初始化服务（需要实现）：

```python
import asyncpg
from ai_runtime.core.embeddings import SentenceTransformerEmbedding
from ai_runtime.core.repositories.knowledge_base import KnowledgeBaseRepository
from ai_runtime.core.services.knowledge_base import KnowledgeBaseService

# 创建数据库连接池
db_pool = await asyncpg.create_pool(
    host="localhost",
    port=5432,
    user="ai_user",
    password="your_password",
    database="ai_platform"
)

# 初始化服务
embedding_service = SentenceTransformerEmbedding()
repository = KnowledgeBaseRepository(db_pool)
kb_service = KnowledgeBaseService(repository, embedding_service)

# 在依赖注入中提供
async def get_kb_service() -> KnowledgeBaseService:
    return kb_service
```

### 4. 配置认证（TODO）

当前API端点中的认证函数需要实现：

```python
# 在 knowledge_base.py 中替换
async def get_current_tenant_id() -> str:
    # TODO: 从JWT token或请求头中提取
    # 示例：从Authorization header解析
    pass

async def get_current_user_id() -> Optional[str]:
    # TODO: 从JWT token中提取
    pass
```

## 性能优化建议

### 1. 使用pgvector扩展（可选）

PostgreSQL的pgvector扩展可以显著提升向量搜索性能：

```sql
-- 安装扩展
CREATE EXTENSION vector;

-- 修改embedding列类型
ALTER TABLE documents ALTER COLUMN embedding TYPE vector(384);

-- 创建索引
CREATE INDEX ON documents USING ivfflat (embedding vector_cosine_ops);
```

### 2. 批量处理

对于大量文档，使用批量创建端点：

```python
# 一次创建最多100个文档
response = requests.post(f"{BASE_URL}/documents/batch", json={
    "documents": [{"title": f"Doc{i}", "content": f"Content{i}"} for i in range(100)]
})
```

### 3. 异步处理

对于大文件或URL抓取，考虑使用后台任务队列（如Celery）异步处理。

## 故障排查

### 问题1: 导入错误

```
ImportError: No module named 'sentence_transformers'
```

**解决**: 安装依赖

```bash
pip install sentence-transformers torch
```

### 问题2: 数据库字段不存在

```
asyncpg.exceptions.UndefinedColumnError: column "embedding" does not exist
```

**解决**: 运行数据库迁移

```bash
psql -U postgres -d ai_platform < db/migrations/001_initial_schema.sql
psql -U postgres -d ai_platform < db/migrations/002_knowledge_base_enhancements.sql
psql -U postgres -d ai_platform < db/migrations/004_add_knowledge_bases.sql
psql -U postgres -d ai_platform < db/migrations/005_migrate_existing_documents.sql
# 可选：pgvector优化（需要先安装pgvector扩展）
# psql -U postgres -d ai_platform < db/migrations/003_enable_pgvector.sql
```

### 问题3: PDF解析失败

```
ImportError: No module named 'PyPDF2'
```

**解决**: 安装PDF解析器

```bash
pip install PyPDF2
```

### 问题4: 模型下载慢

首次运行时sentence-transformers会下载模型，可以：

1. 预先下载模型
```python
from sentence_transformers import SentenceTransformer
model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
```

2. 或使用国内镜像（设置HF_ENDPOINT环境变量）
```bash
export HF_ENDPOINT=https://hf-mirror.com
```

## API文档

启动服务后访问：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 下一步工作

1. **实现认证中间件**: 完成JWT token验证
2. **添加日志审计**: 记录所有文档操作到audit_logs表
3. **实现配额控制**: 限制租户文档数量和存储大小
4. **添加文档版本控制**: 支持文档历史版本
5. **优化搜索性能**: 集成Elasticsearch或pgvector
6. **添加文档分块**: 支持大文档自动分块索引
7. **实现文档标签系统**: 支持多维度分类

## 联系方式

如有问题，请查看完整API文档：http://localhost:8000/docs
