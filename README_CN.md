# AI Platform

[English](./README.md) | 简体中文

这个仓库是一个完整的 AI 应用平台，当前由三个核心服务组成：

- `frontend-vue`：Vue 3 前端
- `platform`：Go 平台层，负责认证、会话、网关代理与对外 API
- `ai_runtime`：Python FastAPI + gRPC 运行时，负责聊天、知识库和模型管理

仓库里的说明文档现在只保留两份：

- `README.md`
- `README_CN.md`

后续如果需要补充文档，只维护这两份即可。

## 当前项目范围

当前代码已经包含：

- JWT 注册、登录、刷新、登出、当前用户接口
- 同步 HTTP、SSE、WebSocket 三种聊天接口
- 会话持久化、聊天历史、用量统计、消息反馈
- 知识库 CRUD、文档上传/导入/搜索、文档预览、分段查看
- 检索设置、快速检索测试、评测数据集、评测运行、评测结果一键应用
- `openai`、`deepseek`、`local`、`mock`、`jina` 五类模型配置管理
- `txt`、`md`、`pdf`、`html`、`csv`、`tsv`、`json`、`jsonl`、`yaml`、`xml`、`rtf`、`docx`、`pptx`、`xlsx` 文档解析
- 由 Alembic 统一管理的 PostgreSQL schema，覆盖认证、聊天、知识库、模型、配额、检索评测、全文搜索、分块索引

当前 Docker 部署实际使用的是 PostgreSQL、Redis 和 Qdrant，Elasticsearch 不在现行 compose 编排中。

## 架构说明

```text
浏览器
  |
  v
Vue 3 前端
  |
  v
Go 平台层 (:8080)
  |- JWT 认证
  |- 限流 / 内容防护 / 成本统计
  |- 会话与聊天接口
  |- 知识库与模型接口反向代理
  |
  +--> Python AI Runtime HTTP (:8000)
  |      |- FastAPI 文档
  |      |- 知识库 / 文档 / 模型接口
  |      |- 可选 HTTP 聊天接口
  |
  +--> Python AI Runtime gRPC (:50051)
         |- 流式聊天后端

PostgreSQL + Qdrant
Redis
```

## 项目结构

```text
.
|-- ai_runtime/              # Python AI Runtime
|-- db/alembic/             # Alembic 迁移目录
|-- frontend-vue/            # Vue 3 前端
|-- nginx/                   # Nginx 网关配置
|-- platform/                # Go 平台层
|-- proto/                   # 共享 proto 定义
|-- scripts/                 # 辅助脚本
|-- docker-compose.infra.yml
|-- docker-compose.backend.yml
|-- docker-compose.frontend.yml
|-- Makefile                 # 统一操作入口
|-- README.md
`-- README_CN.md
```

## 快速开始

### 前置要求

- Docker Engine 和 Compose 插件
- GNU Make
- Git

### 本地开发

开发环境现在统一改为各服务目录直接启动，仓库里不再保留单独的 Docker Compose 开发栈。

常用本地命令：

```bash
cd frontend-vue && npm install && npm run dev -- --host 0.0.0.0
cd platform && go run main.go
cd ai_runtime && pip install -r requirements.txt && python -m main --mode both --http-port 8000 --grpc-port 50051
make test
```

### 统一部署

当前项目只保留这三份拆分编排文件：

- `docker-compose.infra.yml`
- `docker-compose.backend.yml`
- `docker-compose.frontend.yml`，仅用于构建和发布前端静态资源

全新环境推荐顺序：

```bash
make infra-up
make db-upgrade
make backend-up
make frontend-build
```

如果本地镜像已经准备好，也可以走受保护的一键启动：

```bash
make prod-check
make prod
```

重构镜像命令：

```bash
make infra-build
make backend-build
make frontend-build
```

低 I/O 重构命令：

```bash
make infra-build-safe
make ai-runtime-build-safe
make platform-build-safe
make frontend-build-safe
```

运维常用命令：

```bash
make infra-logs
make backend-logs
make frontend-logs
make prod-down
```

数据库常用命令：

```bash
make db-upgrade
make db-current
make db-history
make db-revision m=add_some_change
```

## 环境变量文件

当前主要有三份配置模板：

- `./.env.example`：公共部署配置，例如 `JWT_SECRET`、数据库、域名、SSL
- `./ai_runtime/.env.example`：AI Runtime 配置，例如嵌入模型、配额、RAG、端口
- `./platform/.env.example`：Go 平台层配置，例如 Runtime 地址、JWT 密钥

如果本地环境和仓库默认值不同，先复制并修改这些示例文件。

当前最关键的几个配置：

- `JWT_SECRET`：生产环境必须替换
- `EMBEDDING_PROVIDER`：支持 `local`、`openai`、`jina`
- `LLM_PROVIDER`：支持 `openai`、`deepseek`、`local`、`mock`
- `QDRANT_HOST` / `QDRANT_PORT`：指定独立向量库地址
- `AI_RUNTIME_CHAT_TRANSPORT`：Go 平台层可切换 `grpc` 或 `http` 调用聊天能力

## 前端能力

当前 Vue 前端已包含：

- 登录和注册
- 流式聊天工作台
- 历史会话
- 用量与成本统计
- 模型管理
- 知识库列表、新建、编辑、详情、设置、检索测试页面

前端单独启动方式：

```bash
cd frontend-vue
npm install
npm run dev -- --host 0.0.0.0
```

前端通过 `VITE_API_BASE_URL` 指向后端；如果不配置，默认走相对路径。
生产环境前端发布现在会把静态文件构建到 `frontend-dist/releases/<version>`，并更新 `frontend-dist/current`，由共享的基础设施 nginx 直接托管。

## Platform 服务

Go 平台层是用户直接访问的后端，当前提供：

- `GET /health`
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `GET /api/v1/auth/me`
- `POST /api/v1/auth/logout`
- `POST /api/v1/chat`
- `POST /api/v1/chat/sse`
- `WS /api/v1/chat/ws`
- `GET /api/v1/chat/sessions`
- `GET /api/v1/chat/history/{session_id}`
- `GET /api/v1/chat/usage/stats`
- `GET /api/v1/chat/feedback/low-quality`
- `POST /api/v1/chat/messages/{id}/feedback`
- 代理 `/api/v1/knowledge-bases/*`
- 代理 `/api/v1/knowledge/*`
- 代理 `/api/v1/models/*`

平台层单独启动方式：

```bash
cd platform
go run main.go
```

## AI Runtime

Python Runtime 同时运行 HTTP 和 gRPC 服务，负责 AI 侧核心逻辑。

主要职责：

- 聊天生成
- 知识库管理
- 文档解析、切分、检索
- 检索评测
- LLM 模型存储与选择

单独启动方式：

```bash
cd ai_runtime
pip install -r requirements.txt
python -m main --mode both --http-port 8000 --grpc-port 50051
```

FastAPI 文档入口：

- `http://localhost:8000/docs`

## 数据库与迁移

数据库现在只通过 `db/alembic/` 下的 Alembic 进行管理。

升级到最新 schema：

```bash
make db-upgrade
```

创建新的 revision：

```bash
make db-revision m=describe_change
```

如果要保留现有数据，并把数据库重建到 Alembic baseline：

```bash
make db-reset-to-alembic
```

如果是把已有知识库数据恢复到一个新的部署环境，还需要执行下面的命令重建原生 Qdrant 索引：

```bash
make qdrant-backfill
```

当前在线部署实际使用的数据服务：

- PostgreSQL
- Redis
- Qdrant

## 演示账号

Go 平台层启动时会尝试写入一个演示账号：

```text
Email: demo@example.com
Password: demo123456
```

## 说明

- `make prod` 只是当前拆分部署流程的整体验证与启动别名。
- `make frontend-build` 现在只发布静态资源，生产环境不再有独立的前端容器。
- `FRONTEND_NODE_IMAGE` 默认使用官方 `node:20-alpine`，只有在你需要切到其他内部镜像源时才需要覆盖。
- 如果 `ai_runtime/.env` 中设置了 `EMBEDDING_PROVIDER=local`，`make prod-check` 会要求额外传入 `ALLOW_LOCAL_EMBEDDING=1` 才允许继续。
- `scripts/` 目录里部分脚本仍使用旧的 `docker-compose` 写法，当前应优先以 `Makefile` 为准。
