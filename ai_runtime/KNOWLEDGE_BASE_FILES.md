# 知识库功能 - 新增文件清单

## 文件结构

```
ai_runtime/
├── api/
│   └── knowledge_base.py              # 知识库HTTP API路由（新增）
│
├── core/
│   ├── models/
│   │   └── knowledge_base.py          # 数据模型和Pydantic schemas（新增）
│   │
│   ├── embeddings/                    # 向量嵌入服务（新增）
│   │   ├── __init__.py
│   │   ├── base.py                    # 抽象基类
│   │   └── sentence_transformer.py   # sentence-transformers实现
│   │
│   ├── repositories/                  # 数据访问层（新增）
│   │   └── knowledge_base.py          # 知识库数据库操作
│   │
│   ├── services/                      # 业务逻辑层（新增）
│   │   └── knowledge_base.py          # 知识库服务
│   │
│   ├── parsers/                       # 文件解析器（新增）
│   │   ├── file_parser.py             # 文件解析（TXT/PDF/MD/HTML）
│   │   └── url_fetcher.py             # URL内容抓取
│   │
│   └── rag/
│       └── retriever.py               # 添加DatabaseVectorStore类（修改）
│
├── requirements.txt                   # 添加新依赖（修改）
└── KNOWLEDGE_BASE_API.md              # API使用文档（新增）

db/migrations/
├── 002_knowledge_base_enhancements.sql  # 数据库迁移脚本（新增）
├── 004_add_knowledge_bases.sql          # 知识库表与关联（新增）
└── 005_migrate_existing_documents.sql   # 迁移已有文档（新增）
```

## 核心组件说明

### 1. API层 (`api/knowledge_base.py`)
- 10个HTTP端点
- RESTful API设计
- 完整的增删改查
- 文件上传、URL抓取、批量处理
- 向量语义搜索

### 2. 数据模型 (`core/models/knowledge_base.py`)
- `Document`: 文档数据模型
- `CreateDocumentRequest`: 创建请求
- `UpdateDocumentRequest`: 更新请求
- `DocumentResponse`: API响应
- `SearchDocumentsRequest/Response`: 搜索相关
- `BatchCreateRequest/Response`: 批量处理

### 3. 向量嵌入 (`core/embeddings/`)
- `EmbeddingService`: 抽象基类
- `SentenceTransformerEmbedding`: 本地多语言模型
- 支持单个/批量文本转向量
- 余弦相似度计算

### 4. 数据访问 (`core/repositories/knowledge_base.py`)
- `KnowledgeBaseRepository`: 数据库CRUD
- 支持权限过滤（租户级+用户级）
- 向量相似度搜索
- 分页查询

### 5. 业务逻辑 (`core/services/knowledge_base.py`)
- `KnowledgeBaseService`: 业务逻辑封装
- 自动向量索引
- 文件上传处理
- URL内容抓取
- 批量创建

### 6. 文件解析 (`core/parsers/`)
- `FileParser`: 抽象基类
- `TextParser`: 纯文本
- `MarkdownParser`: Markdown
- `PDFParser`: PDF文档
- `HTMLParser`: 网页
- `URLFetcher`: URL内容抓取

### 7. RAG集成 (`core/rag/retriever.py`)
- `DatabaseVectorStore`: 数据库向量存储
- 与现有RAG系统无缝集成
- 保持向后兼容

## 依赖关系

```
HTTP API (knowledge_base.py)
    ↓
Service Layer (services/knowledge_base.py)
    ↓ ↙ ↘
Repository  Embedding  Parsers
    ↓         ↓          ↓
Database  Model    File/URL
```

## 安装步骤

1. **运行数据库迁移**
```bash
psql -U postgres -d ai_platform < db/migrations/001_initial_schema.sql
psql -U postgres -d ai_platform < db/migrations/002_knowledge_base_enhancements.sql
psql -U postgres -d ai_platform < db/migrations/004_add_knowledge_bases.sql
psql -U postgres -d ai_platform < db/migrations/005_migrate_existing_documents.sql
# 可选：pgvector优化（需要先安装pgvector扩展）
# psql -U postgres -d ai_platform < db/migrations/003_enable_pgvector.sql
```

2. **安装Python依赖**
```bash
cd ai_runtime
pip install -r requirements.txt
```

3. **首次运行（自动下载模型）**
```bash
python main.py
```

## API测试

启动服务后访问：
- http://localhost:8000/docs (Swagger UI)
- http://localhost:8000/api/v1/knowledge/documents

## 关键特性

- ✅ 完整CRUD操作
- ✅ 多格式文件支持（TXT/PDF/MD/HTML）
- ✅ URL内容自动抓取
- ✅ 批量导入（最多100条）
- ✅ 向量语义搜索
- ✅ 租户+用户双层权限
- ✅ 自动向量索引
- ✅ 本地多语言模型
- ✅ 与现有RAG系统集成
- ✅ 异步IO设计

## TODO（待实现）

- [ ] 实现JWT认证中间件
