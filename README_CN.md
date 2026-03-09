# AI Platform - 企业级 AI 应用平台

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Go Version](https://img.shields.io/badge/Go-1.21+-00ADD8?logo=go)](https://golang.org/)
[![Python Version](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python)](https://www.python.org/)

一个生产就绪的 AI 应用平台，采用 Go (平台层) 和 Python (AI 运行时) 微服务架构，通过 gRPC 流式通信。

[English](./README.md) | 简体中文

## 🌟 核心特性

### 前端 (Vue 3)
- ✅ **现代化界面** - 清爽响应式设计
- ✅ **实时聊天** - SSE 流式响应
- ✅ **知识库管理** - 文档上传、搜索、管理
- ✅ **会话管理** - 多会话支持
- ✅ **移动端适配** - 全设备支持

### 平台层 (Go)
- ✅ **JWT 认证** - 完整的用户注册/登录系统
- ✅ **多租户支持** - 租户隔离和管理
- ✅ **限流中间件** - Token Bucket 算法
- ✅ **内容安全** - 请求过滤和安全检查
- ✅ **成本追踪** - Token 使用计量和成本计算
- ✅ **多协议支持** - HTTP/SSE/WebSocket
- ✅ **API 代理** - 知识库 API 反向代理

### AI 运行时 (Python)
- ✅ **知识库系统** - 文档管理、向量搜索
- ✅ **RAG 管道** - 检索增强生成
- ✅ **LLM 集成** - OpenAI 和本地模型支持
- ✅ **Agent 系统** - 工具使用型 Agent
- ✅ **流式处理** - 完整的流式输出支持
- ✅ **文件解析** - PDF、Markdown、HTML 支持

### 数据库
- ✅ **PostgreSQL + pgvector** - 用户、会话、文档、向量存储
- ✅ **Redis** - 缓存、Token 黑名单、限流
- ✅ **Elasticsearch** - 全文搜索、日志

## 📋 目录

- [快速开始](#快速开始)
- [架构设计](#架构设计)
- [项目结构](#项目结构)
- [开发环境](#开发环境)
- [生产部署](#生产部署)
- [API 文档](#api-文档)
- [配置说明](#配置说明)

---

## 🚀 快速开始

### 前置要求

- Docker & Docker Compose
- Git

### 开发环境（支持热重载）

```bash
# 克隆项目
git clone <repository-url>
cd ai-platform

# 启动开发环境
make dev

# 或使用 docker-compose
docker-compose -f docker-compose.yml -f docker-compose.dev.yml --profile full up -d
```

拆分编排请参考 [docs/DOCKER_COMPOSE_SPLIT.md](/mnt/ai-platform/docs/DOCKER_COMPOSE_SPLIT.md)。

**访问地址：**
- 前端（Vite 开发服务器）: http://localhost:5173
- 后端 API: http://localhost:8080
- AI Runtime: http://localhost:8000
- PostgreSQL: localhost:5433
- Redis: localhost:6379
- Elasticsearch: http://localhost:9200

**开发环境特性：**
- ✅ 代码热重载（Python watchdog、Go Air、Vite HMR）
- ✅ 源码挂载到容器，实时修改生效
- ✅ 暴露所有端口便于调试
- ✅ 详细的调试日志

### 生产环境（完全容器化）

```bash
# 启动生产环境
make prod

# 或使用 docker-compose
docker-compose -f docker-compose.yml -f docker-compose.prod.yml --profile full up -d
```

如果需要让基础设施、后端、前端独立更新镜像，请改用拆分文件：
[docs/DOCKER_COMPOSE_SPLIT.md](/mnt/ai-platform/docs/DOCKER_COMPOSE_SPLIT.md)

**访问地址：**
- HTTP: http://localhost
- HTTPS: https://your-domain.com（需配置域名和证书）

**生产环境特性：**
- ✅ 完全容器化，不依赖宿主机
- ✅ 优化的资源限制
- ✅ 健康检查和自动重启
- ✅ 仅暴露必要端口（80/443）

### 测试账号

```
Email: demo@example.com
Password: demo123456
```

---

## 🏗️ 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                         Nginx Gateway                        │
│                      (80/443, SSL/TLS)                       │
└────────────────────────┬────────────────────────────────────┘
                         │
         ┌───────────────┴───────────────┐
         │                               │
         ▼                               ▼
┌─────────────────┐            ┌─────────────────┐
│  Vue Frontend   │            │  Go Platform    │
│   (Nginx)       │            │   Layer         │
│                 │            │                 │
│  - 用户界面     │            │  - JWT 认证     │
│  - 知识库管理   │            │  - 限流         │
│  - 聊天界面     │            │  - 成本追踪     │
└─────────────────┘            │  - API 代理     │
                               └────────┬────────┘
                                        │
                        ┌───────────────┴───────────────┐
                        │                               │
                        ▼ (gRPC)                        ▼ (HTTP)
                ┌──────────────┐              ┌──────────────┐
                │ Chat Service │              │ Knowledge    │
                │   (gRPC)     │              │   Base API   │
                └──────────────┘              └──────────────┘
                        │                               │
                        └───────────┬───────────────────┘
                                    ▼
                        ┌─────────────────────┐
                        │  Python AI Runtime  │
                        │                     │
                        │  - LLM 集成         │
                        │  - RAG 管道         │
                        │  - 向量搜索         │
                        │  - 文件解析         │
                        └──────────┬──────────┘
                                   │
                ┌──────────────────┼──────────────────┐
                ▼                  ▼                  ▼
        ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
        │ PostgreSQL   │  │    Redis     │  │Elasticsearch │
        │  + pgvector  │  │              │  │              │
        └──────────────┘  └──────────────┘  └──────────────┘
```

### 通信流程

1. **认证流程**: 用户 → Nginx → Platform (JWT) → 返回 Token
2. **聊天流程**: 用户 → Nginx → Platform → AI Runtime (gRPC) → LLM → 流式返回
3. **知识库流程**: 用户 → Nginx → Platform (HTTP 代理) → AI Runtime → PostgreSQL

---

## 📁 项目结构

```
ai-platform/
├── frontend-vue/              # Vue 3 前端
│   ├── src/
│   │   ├── api/              # API 调用
│   │   ├── components/       # 可复用组件
│   │   ├── views/            # 页面视图
│   │   ├── store/            # Pinia 状态管理
│   │   └── router/           # Vue Router
│   ├── Dockerfile            # 生产构建
│   └── Dockerfile.dev        # 开发构建
│
├── platform/                  # Go 平台层
│   ├── main.go               # 主入口
│   ├── api/
│   │   ├── http/             # HTTP 处理器
│   │   └── grpc/             # gRPC 客户端
│   ├── middleware/           # 中间件
│   ├── auth/                 # 认证服务
│   ├── service/              # 业务逻辑
│   ├── proto/chat/           # Protobuf 生成文件
│   ├── Dockerfile            # 生产构建
│   └── .air.toml             # 热重载配置
│
├── ai_runtime/                # Python AI 运行时
│   ├── main.py               # 主入口
│   ├── api/
│   │   ├── http_server.py    # FastAPI HTTP 服务
│   │   ├── grpc_server.py    # gRPC 服务
│   │   ├── chat_service.py   # 聊天服务
│   │   └── knowledge_base.py # 知识库 API
│   ├── core/
│   │   ├── services/         # 业务逻辑
│   │   ├── repositories/     # 数据访问
│   │   ├── models/           # 数据模型
│   │   ├── embeddings/       # 向量嵌入
│   │   └── parsers/          # 文件解析
│   ├── Dockerfile            # 生产构建
│   └── requirements.txt      # Python 依赖
│
├── nginx/                     # Nginx 网关
│   ├── Dockerfile
│   ├── nginx.conf
│   └── conf.d/
│
├── db/migrations/             # 数据库迁移
│   ├── 001_initial_schema.sql
│   ├── 002_knowledge_base_enhancements.sql
│   └── 003_enable_pgvector.sql
│
├── proto/                     # Protobuf 定义
│   └── chat_service.proto
│
├── docker-compose.yml         # 基础配置
├── docker-compose.dev.yml     # 开发环境配置
├── docker-compose.prod.yml    # 生产环境配置
├── docker-compose.infra.yml   # 基础设施独立编排
├── docker-compose.backend.yml # 后端独立编排
├── docker-compose.frontend.yml# 前端独立编排
├── Makefile                   # 便捷命令
├── .env                       # 环境变量
└── README_CN.md               # 本文档
```

---

## 💻 开发环境

### 启动开发环境

```bash
# 使用 Makefile（推荐）
make dev

# 查看日志
make dev-logs

# 停止
make dev-down
```

### 开发环境特性

**代码热重载：**
- **Python**: watchdog 自动重启
- **Go**: Air 热重载
- **Vue**: Vite HMR

**源码挂载：**
```yaml
ai-runtime:
  volumes:
    - ./ai_runtime:/app:rw              # 挂载源码
    - huggingface_cache:/root/.cache    # 缓存持久化

platform:
  volumes:
    - ./platform:/src/platform:rw       # 挂载源码
    - platform_build_cache:/go/pkg      # Go 构建缓存

frontend:
  volumes:
    - ./frontend-vue:/app:rw            # 挂载源码
    - /app/node_modules                 # 排除 node_modules
```

### 修改代码

1. 修改 Python 代码 → 自动重启 AI Runtime
2. 修改 Go 代码 → Air 自动重新编译
3. 修改 Vue 代码 → Vite HMR 即时更新

### 调试

```bash
# 查看特定服务日志
docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f platform
docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f ai-runtime
docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f frontend

# 进入容器
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec platform sh
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec ai-runtime bash

# 连接数据库
make db-shell

# 连接 Redis
make redis-cli
```

---

## 🚢 生产部署

### 启动生产环境

```bash
# 推荐：按拆分后的层级分别启动
make infra-up
make backend-up
make frontend-up

# 查看日志
make infra-logs
make backend-logs
make frontend-logs

# 停止
make frontend-down
make backend-down
make infra-down
```

整栈兼容命令仍然保留：

```bash
make prod
make prod-build
make prod-down
```

### 生产环境特性

**完全容器化：**
- ❌ 不挂载源码
- ✅ 使用构建时复制的代码
- ✅ 容器独立运行

**资源限制：**
```yaml
ai-runtime:
  deploy:
    resources:
      limits:
        cpus: '2'
        memory: 4G
      reservations:
        cpus: '1'
        memory: 2G
```

**健康检查：**
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 40s
```

**自动重启：**
```yaml
restart: always
```

### 配置域名和 SSL

1. 修改 `.env` 文件：
```bash
DOMAIN=your-domain.com
EMAIL=admin@your-domain.com
LETSENCRYPT_STAGING=0
```

2. 重启 Nginx：
```bash
docker-compose restart nginx
```

3. 获取 SSL 证书：
```bash
docker-compose exec certbot certbot certonly \
  --webroot -w /var/www/certbot \
  -d your-domain.com \
  --email admin@your-domain.com \
  --agree-tos
```

---

## 📚 API 文档

### 认证 API

**注册**
```http
POST /api/v1/auth/register
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "password123"
}
```

**登录**
```http
POST /api/v1/auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "password123"
}

Response:
{
  "access_token": "eyJhbGc...",
  "refresh_token": "eyJhbGc...",
  "user": {
    "id": "user-id",
    "email": "user@example.com"
  }
}
```

**获取当前用户**
```http
GET /api/v1/auth/me
Authorization: Bearer <access_token>
```

### 聊天 API

**同步聊天**
```http
POST /api/v1/chat
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "session_id": "session-123",
  "message": "你好",
  "config": {
    "use_rag": false,
    "use_agent": false,
    "temperature": 0.7,
    "max_tokens": 2000
  }
}
```

**流式聊天（SSE）**
```http
POST /api/v1/chat/sse
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "session_id": "session-123",
  "message": "你好"
}

Response: (Server-Sent Events)
data: {"type": 1, "content": "你"}
data: {"type": 1, "content": "好"}
data: [DONE]
```

### 知识库 API

**列出文档**
```http
GET /api/v1/knowledge/documents?page=1&page_size=20
Authorization: Bearer <access_token>

Response:
{
  "documents": [...],
  "total": 100,
  "page": 1,
  "page_size": 20
}
```

**创建文档**
```http
POST /api/v1/knowledge/documents
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "title": "文档标题",
  "content": "文档内容",
  "source": "manual",
  "source_type": "manual",
  "access_level": "tenant",
  "auto_index": true
}
```

**上传文件**
```http
POST /api/v1/knowledge/documents/upload
Authorization: Bearer <access_token>
Content-Type: multipart/form-data

file: <file>
access_level: tenant
auto_index: true
```

**搜索文档**
```http
POST /api/v1/knowledge/documents/search
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "query": "搜索关键词",
  "top_k": 10
}

Response:
{
  "results": [
    {
      "document": {...},
      "score": 0.95
    }
  ],
  "total": 10
}
```

**获取统计**
```http
GET /api/v1/knowledge/stats
Authorization: Bearer <access_token>

Response:
{
  "total_documents": 100,
  "indexed_documents": 95,
  "by_source_type": {
    "manual": 50,
    "file": 30,
    "url": 20
  }
}
```

---

## ⚙️ 配置说明

### 环境变量

**根目录 `.env`**
```bash
# JWT 密钥
JWT_SECRET=your-secret-key-change-this-in-production

# 数据库配置
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=ai_platform
POSTGRES_USER=ai_platform
POSTGRES_PASSWORD=19980912

# Redis
REDIS_HOST=redis
REDIS_PORT=6379

# Elasticsearch
ELASTICSEARCH_URL=http://elasticsearch:9200

# 域名配置（生产环境）
DOMAIN=your-domain.com
EMAIL=admin@your-domain.com
```

**ai_runtime/.env**
```bash
# 嵌入模型配置
EMBEDDING_PROVIDER=local
EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2
EMBEDDING_DEVICE=cpu

# LLM 配置
LLM_PROVIDER=openai
OPENAI_API_KEY=your-api-key
OPENAI_API_BASE=https://api.openai.com/v1

# RAG 配置
ENABLE_RAG=true
RAG_TOP_K=5
RAG_SIMILARITY_THRESHOLD=0.7

# Agent 配置
ENABLE_AGENT=true
AGENT_MAX_ITERATIONS=10
```

### Makefile 命令

```bash
# 查看所有命令
make help

# 开发环境
make dev              # 启动开发环境
make dev-build        # 重新构建并启动
make dev-logs         # 查看日志
make dev-down         # 停止

# 生产环境
make infra-up         # 启动基础设施
make backend-up       # 启动后端
make frontend-up      # 启动前端
make infra-build      # 重构基础设施镜像
make backend-build    # 重构后端镜像
make frontend-build   # 重构前端镜像
make infra-logs       # 查看基础设施日志
make backend-logs     # 查看后端日志
make frontend-logs    # 查看前端日志
make prod             # 兼容的整栈启动命令
make prod-build       # 兼容的整栈重构命令
make prod-down        # 兼容的整栈停止命令

# 数据库管理
make db-migrate       # 运行数据库迁移
make db-shell         # 连接到 PostgreSQL
make redis-cli        # 连接到 Redis

# 服务管理
make restart-platform
make restart-ai-runtime
make restart-frontend
```

---

## 🔧 故障排查

### 查看日志

```bash
# 开发环境全部日志
make dev-logs

# 生产环境拆分日志
make infra-logs
make backend-logs
make frontend-logs
```

### 进入容器

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec platform sh
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec ai-runtime bash
docker compose -f docker-compose.infra.yml exec postgres psql -U ai_platform -d ai_platform
```

### 重启服务

```bash
make restart-platform
make restart-ai-runtime
make restart-frontend
make restart-nginx
```

### 清理并重建

```bash
make clean
make dev-build
```

---

## 📝 常见问题

**Q: 如何切换 LLM 提供商？**

A: 修改 `ai_runtime/.env` 中的 `LLM_PROVIDER` 和相关配置。

**Q: 如何添加新的嵌入模型？**

A: 修改 `ai_runtime/.env` 中的 `EMBEDDING_PROVIDER` 和 `EMBEDDING_MODEL`。

**Q: 如何备份数据？**

A:
```bash
# 备份 PostgreSQL
docker-compose exec postgres pg_dump -U ai_platform ai_platform > backup.sql

# 恢复
docker-compose exec -T postgres psql -U ai_platform ai_platform < backup.sql
```

**Q: 如何查看 API 文档？**

A: 访问 http://localhost:8000/docs (AI Runtime FastAPI 文档)

---

## 📄 许可证

MIT License

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

## 📧 联系方式

如有问题，请提交 Issue。
