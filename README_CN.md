# AI Platform - 企业级 AI 应用平台

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Go Version](https://img.shields.io/badge/Go-1.21+-00ADD8?logo=go)](https://golang.org/)
[![Python Version](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python)](https://www.python.org/)

一个生产就绪的 AI 应用平台，采用 Go (平台层) 和 Python (AI 运行时) 微服务架构，通过 gRPC 流式通信。

## 🌟 核心特性

### 前端 (Vue 3)
- ✅ **现代化界面** - 清爽响应式设计
- ✅ **实时聊天** - SSE 流式响应
- ✅ **会话管理** - 多会话支持
- ✅ **移动端适配** - 全设备支持
- ✅ **Docker 部署** - 一键容器化部署

### 平台层 (Go)
- ✅ **JWT 认证** - 完整的用户注册/登录系统
- ✅ **多租户支持** - 租户隔离和管理
- ✅ **限流中间件** - Token Bucket 算法
- ✅ **内容安全** - 请求过滤和安全检查
- ✅ **成本追踪** - Token 使用计量和成本计算
- ✅ **多协议支持** - HTTP/SSE/WebSocket
- ✅ **数据库集成** - PostgreSQL + Redis + Elasticsearch

### AI 运行时 (Python)
- ✅ **Prompt 构建器** - 模板化 Prompt 管理
- ✅ **RAG 管道** - 检索增强生成
- ✅ **LLM 集成** - OpenAI 和本地模型支持
- ✅ **Agent 系统** - 工具使用型 Agent
- ✅ **流式处理** - 完整的流式输出支持
- ✅ **中间件管道** - 可扩展的处理链

### 数据库
- ✅ **PostgreSQL** - 用户、会话、消息存储
- ✅ **Redis** - 缓存、Token 黑名单、限流
- ✅ **Elasticsearch** - 向量搜索、RAG 支持

## 📋 目录

- [架构设计](#架构设计)
- [快速开始](#快速开始)
- [项目结构](#项目结构)
- [功能特性](#功能特性)
- [API 文档](#api-文档)
- [数据库配置](#数据库配置)
- [开发指南](#开发指南)
- [部署指南](#部署指南)
- [常见问题](#常见问题)

## 🏗️ 架构设计

```
┌──────────────────────────────┐
│     客户端 (Web/App/CLI)      │
│    Vue 3 前端 (Nginx)         │
└────────────▲─────────────────┘
             │ HTTP/SSE
┌────────────┴─────────────────┐
│      Go 平台层 (中枢)         │
│                               │
│  ✓ JWT 认证                   │
│  ✓ 限流/配额                  │
│  ✓ 成本追踪                   │
│  ✓ 内容安全                   │
│  ✓ 审计日志                   │
└────────────▲─────────────────┘
             │ gRPC Streaming
┌────────────┴─────────────────┐
│    Python AI 运行时 (大脑)    │
│                               │
│  ✓ Prompt Builder            │
│  ✓ RAG Pipeline              │
│  ✓ LLM Integration           │
│  ✓ Agent Executor            │
│  ✓ Stream Processing         │
└────────────▲─────────────────┘
             │
┌────────────┴─────────────────┐
│       数据库基础设施          │
│  PostgreSQL | Redis | ES     │
└──────────────────────────────┘
```

## 🚀 快速开始

### 前置要求

- **Docker & Docker Compose** (推荐)
- **Go 1.21+** (如果本地运行)
- **Python 3.11+** (如果本地运行)
- **PostgreSQL 16** (如果不使用 Docker)
- **Redis 7** (如果不使用 Docker)
- **Elasticsearch 8** (如果不使用 Docker)

### 方式一：使用 Docker Compose (推荐)

```bash
# 1. 克隆仓库
git clone <repository-url>
cd ai-platform

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 设置你的配置

# 3. 启动所有服务
docker-compose --profile full up -d

# 4. 查看日志
docker-compose logs -f
```

访问：
- **前端界面**: http://localhost (或 http://localhost:80)
- **API 服务**: http://localhost:8080
- **Kibana** (可选): http://localhost:5601

### 方式二：仅启动数据库

```bash
# 启动数据库
./scripts/init-databases.sh  # Linux/Mac
# 或
scripts\init-databases.bat   # Windows

# 启动 Python AI Runtime
cd ai_runtime
pip install -r requirements.txt
python main.py

# 启动 Go Platform (新终端)
cd platform
go mod download
go run main.go
```

### 方式三：使用启动脚本

```bash
# Linux/Mac
chmod +x start_dev.sh
./start_dev.sh

# Windows
start_dev.bat
```

## 📁 项目结构

```
ai-platform/
├── frontend-vue/                # Vue 3 前端
│   ├── public/                  # 静态资源
│   ├── src/
│   │   ├── api/                 # API 服务层
│   │   │   ├── axios.js        # Axios 配置
│   │   │   └── index.js        # API 端点
│   │   ├── assets/             # 资源文件
│   │   ├── components/         # 可复用组件
│   │   ├── router/             # 路由配置
│   │   ├── store/              # Pinia 状态管理
│   │   │   ├── auth.js         # 认证状态
│   │   │   ├── chat.js         # 聊天状态
│   │   │   └── knowledge.js    # 知识库状态
│   │   ├── views/              # 页面组件
│   │   ├── App.vue             # 根组件
│   │   └── main.js             # 入口文件
│   ├── Dockerfile              # Docker 构建文件
│   ├── nginx.conf              # Nginx 配置
│   ├── package.json
│   └── vite.config.js
│
├── platform/                    # Go 平台层
│   ├── api/
│   │   ├── http/               # HTTP/SSE/WebSocket 处理器
│   │   │   ├── auth_handler.go
│   │   │   └── chat_handler.go
│   │   └── grpc/               # gRPC 客户端
│   │       └── ai_client.go
│   ├── auth/                    # JWT 认证
│   │   ├── jwt.go
│   │   ├── user.go
│   │   └── service.go
│   ├── database/                # 数据库集成
│   │   ├── postgres.go
│   │   ├── redis.go
│   │   ├── elasticsearch.go
│   │   ├── user_store.go
│   │   └── session_store.go
│   ├── middleware/              # 中间件
│   │   ├── auth.go
│   │   ├── rate_limit.go
│   │   ├── guard.go
│   │   └── cost.go
│   ├── service/                 # 业务逻辑
│   │   ├── chat_service.go
│   │   └── session_service.go
│   ├── main.go
│   └── go.mod
│
├── ai_runtime/                  # Python AI 运行时
│   ├── api/
│   │   └── chat_service.py
│   ├── core/
│   │   ├── prompt/             # Prompt 管理
│   │   ├── rag/                # RAG 管道
│   │   ├── llm/                # LLM 集成
│   │   ├── agent/              # Agent 执行器
│   │   └── stream/             # 流处理
│   ├── main.py
│   └── requirements.txt
│
├── db/
│   └── migrations/             # 数据库迁移
│       └── 001_initial_schema.sql
│
├── docs/                        # 文档
│   ├── DATABASE_GUIDE.md
│   ├── JWT_AUTHENTICATION.md
│   └── JWT_IMPLEMENTATION_SUMMARY.md
│
├── examples/                    # 示例
│   ├── auth_examples.sh
│   ├── api_examples.sh
│   └── websocket_client_jwt.html
│
├── scripts/                     # 工具脚本
│   ├── init-databases.sh
│   └── generate_proto.sh
│
├── proto/                       # gRPC 协议定义
│   └── chat_service.proto
│
├── docker-compose.yml
├── .env.example
└── README_CN.md                # 本文件
```

## ✨ 功能特性

### 1. JWT 认证系统

完整的用户认证和授权系统：

```bash
# 注册用户
curl -X POST http://localhost:8080/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"password123"}'

# 登录
curl -X POST http://localhost:8080/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@example.com","password":"demo123456"}'
```

**Demo 用户：**
- Email: `demo@example.com`
- Password: `demo123456`

详细文档：[docs/JWT_AUTHENTICATION.md](docs/JWT_AUTHENTICATION.md)

### 2. 聊天 API

支持三种模式的聊天接口：

#### 同步聊天
```bash
curl -X POST http://localhost:8080/api/v1/chat \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "session_001",
    "message": "Hello!",
    "config": {"use_rag": false, "use_agent": false}
  }'
```

#### 流式聊天 (SSE)
```bash
curl -X POST http://localhost:8080/api/v1/chat/sse \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"session_id":"session_002","message":"Tell me a story"}'
```

#### WebSocket 聊天
```javascript
const ws = new WebSocket('ws://localhost:8080/api/v1/chat/ws');
// 详见 examples/websocket_client_jwt.html
```

### 3. 数据库集成

#### PostgreSQL
- 用户管理
- 会话历史
- 消息存储
- Token 使用追踪
- 审计日志

#### Redis
- API 响应缓存
- JWT Token 黑名单
- 会话数据
- 分布式限流

#### Elasticsearch
- 向量搜索 (RAG)
- 文档索引
- 语义搜索

详细文档：[docs/DATABASE_GUIDE.md](docs/DATABASE_GUIDE.md)

### 4. RAG (检索增强生成)

```python
# 添加文档到向量库
from core.rag import RAGPipeline, Document

documents = [
    Document(content="文档内容...", metadata={"source": "doc1.pdf"}),
]
await rag_pipeline.add_documents(documents)

# 使用 RAG 查询
context = await rag_pipeline.process("用户问题", top_k=5)
```

### 5. Agent 工具系统

```python
# 内置工具
- get_current_time: 获取当前时间
- calculator: 执行计算

# 使用 Agent
curl -X POST http://localhost:8080/api/v1/chat \
  -H "Authorization: Bearer <token>" \
  -d '{
    "message": "现在几点了？",
    "config": {"use_agent": true, "tools": ["get_current_time"]}
  }'
```

## 📚 API 文档

### 认证端点

| 方法 | 端点 | 描述 | 认证 |
|------|------|------|------|
| POST | `/api/v1/auth/register` | 用户注册 | 否 |
| POST | `/api/v1/auth/login` | 用户登录 | 否 |
| POST | `/api/v1/auth/refresh` | 刷新 Token | 否 |
| GET | `/api/v1/auth/me` | 获取当前用户 | 是 |
| POST | `/api/v1/auth/logout` | 登出 | 是 |

### 聊天端点

| 方法 | 端点 | 描述 | 认证 |
|------|------|------|------|
| POST | `/api/v1/chat` | 同步聊天 | 是 |
| POST | `/api/v1/chat/sse` | 流式聊天 (SSE) | 是 |
| WS | `/api/v1/chat/ws` | WebSocket 聊天 | 是 |

### 健康检查

| 方法 | 端点 | 描述 |
|------|------|------|
| GET | `/health` | 健康检查 |

完整 API 文档：[docs/JWT_AUTHENTICATION.md](docs/JWT_AUTHENTICATION.md)

## 💾 数据库配置

### 连接信息

**PostgreSQL:**
```
Host: localhost:5432
Database: ai_platform
User: ai_platform
Password: ai_platform_password
```

**Redis:**
```
Host: localhost:6379
```

**Elasticsearch:**
```
URL: http://localhost:9200
```

### 初始化数据库

```bash
# Linux/Mac
./scripts/init-databases.sh

# Windows
scripts\init-databases.bat

# 或使用 Docker Compose
docker-compose up -d postgres redis elasticsearch
```

### 数据库迁移

迁移会在 PostgreSQL 启动时自动运行。手动运行：

```bash
psql -h localhost -U ai_platform -d ai_platform -f db/migrations/001_initial_schema.sql
```

详细文档：[docs/DATABASE_GUIDE.md](docs/DATABASE_GUIDE.md)

## 🔧 开发指南

### 环境配置

1. **复制环境变量模板**
```bash
cp .env.example .env
```

2. **配置关键变量**
```bash
# JWT 密钥 (生产环境必须修改！)
JWT_SECRET=your-super-secret-key-change-in-production

# 数据库
POSTGRES_HOST=localhost
POSTGRES_PASSWORD=your-secure-password

# OpenAI (可选)
OPENAI_API_KEY=your-openai-api-key
```

### 生成 gRPC Stubs

```bash
# Linux/Mac
chmod +x generate_proto.sh
./generate_proto.sh

# Windows
generate_proto.bat
```

### 本地开发

**启动 AI Runtime:**
```bash
cd ai_runtime
pip install -r requirements.txt
python main.py
```

**启动 Platform:**
```bash
cd platform
go mod download
go run main.go
```

### 运行测试

**Go 测试:**
```bash
cd platform
go test ./...
```

**Python 测试:**
```bash
cd ai_runtime
pytest
```

### 代码风格

**Go:**
```bash
gofmt -w .
go vet ./...
```

**Python:**
```bash
black .
flake8
```

## 🚢 部署指南

### Docker 部署

```bash
# 构建镜像
docker-compose build

# 启动所有服务
docker-compose --profile full up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

### Kubernetes 部署

```bash
# 应用配置
kubectl apply -f k8s/

# 查看状态
kubectl get pods
kubectl get services
```

### 生产环境检查清单

- [ ] 修改所有默认密码
- [ ] 设置强 JWT 密钥
- [ ] 启用 HTTPS/TLS
- [ ] 配置防火墙规则
- [ ] 设置数据库备份
- [ ] 配置日志收集
- [ ] 设置监控告警
- [ ] 配置 CDN (如需要)
- [ ] 启用限流
- [ ] 配置错误追踪

### 环境变量 (生产)

```bash
# 安全
JWT_SECRET=<强随机字符串>
POSTGRES_PASSWORD=<强密码>
REDIS_PASSWORD=<强密码>

# 数据库 (使用托管服务)
POSTGRES_HOST=<RDS地址>
REDIS_HOST=<ElastiCache地址>
ELASTICSEARCH_URL=<OpenSearch地址>

# 功能开关
ENVIRONMENT=production
LOG_LEVEL=INFO
ENABLE_TELEMETRY=true
```

## ❓ 常见问题

### Q: 如何修改 JWT 密钥？

A: 在 `.env` 文件中设置 `JWT_SECRET` 环境变量，或在启动时设置：
```bash
export JWT_SECRET="your-new-secret-key"
```

### Q: 如何添加新的 Agent 工具？

A: 在 `ai_runtime/core/agent/tools/` 创建新工具类：
```python
class MyTool(Tool):
    def __init__(self):
        super().__init__("my_tool", "工具描述")

    async def execute(self, **kwargs):
        # 实现工具逻辑
        return result
```

### Q: 如何切换到 OpenAI？

A: 在 `ai_runtime/main.py` 中修改：
```python
from core.llm import OpenAILLM

# 替换 LocalLLM
self.llm = OpenAILLM(
    model="gpt-4",
    api_key=os.getenv("OPENAI_API_KEY")
)
```

### Q: 如何增加 RAG 文档？

A: 使用 Elasticsearch API 或通过代码：
```python
from database import ElasticsearchVectorStore

# 索引文档
doc = VectorDocument(
    id="doc-1",
    tenant_id="tenant-1",
    title="文档标题",
    content="文档内容",
    embedding=vector  # 从嵌入模型获取
)
await vector_store.IndexDocument(ctx, doc)
```

### Q: 数据库连接失败？

A: 检查：
1. 数据库服务是否运行：`docker-compose ps`
2. 连接信息是否正确：查看 `.env`
3. 防火墙规则
4. 查看日志：`docker-compose logs postgres`

### Q: 如何备份数据？

A:
```bash
# PostgreSQL 备份
docker-compose exec postgres pg_dump -U ai_platform ai_platform > backup.sql

# 恢复
docker-compose exec -T postgres psql -U ai_platform ai_platform < backup.sql

# Redis 备份
docker-compose exec redis redis-cli SAVE
```

## 📖 文档索引

- **[快速开始](QUICKSTART.md)** - 5分钟入门
- **[JWT 认证](docs/JWT_AUTHENTICATION.md)** - 完整认证指南
- **[数据库指南](docs/DATABASE_GUIDE.md)** - 数据库配置和使用
- **[API 参考](docs/API_REFERENCE.md)** - 完整 API 文档
- **[部署指南](docs/DEPLOYMENT.md)** - 生产部署
- **[开发指南](docs/DEVELOPMENT.md)** - 开发者文档

## 🤝 贡献

欢迎贡献！请查看 [CONTRIBUTING.md](CONTRIBUTING.md)

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情

## 🙏 致谢

- OpenAI - LLM 支持
- LangChain - AI 框架
- PostgreSQL - 数据库
- Redis - 缓存
- Elasticsearch - 搜索引擎

## 📞 支持

- **问题反馈**: [GitHub Issues](https://github.com/your-org/ai-platform/issues)
- **讨论**: [GitHub Discussions](https://github.com/your-org/ai-platform/discussions)
- **文档**: [docs/](docs/)

---

**使用愉快！如有问题，请查看文档或提交 Issue。** 🚀
