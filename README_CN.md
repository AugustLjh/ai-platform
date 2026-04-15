# AI Platform

[English](./README.md) | 简体中文

这个仓库是一个完整的 AI 应用平台，当前由三个核心服务组成：

- `frontend-vue`：Vue 3 前端
- `platform`：Go 平台层，负责认证、会话、网关代理与对外 API
- `ai_runtime`：Python FastAPI + gRPC 运行时，负责聊天、知识库和模型管理

这个项目并不声称自己已经完整，也不试图把当前状态包装成最终答案。它更像一个开放的起点: 不完美、会持续演进，也带着现实中的各种权衡。之所以把它公开出来，不是为了宣称完成，而是为了让当前的工作可以被看见、被使用、被审视，也更容易被继续扩展和推进。

当前仓库的主要说明文档有三份：

- `README.md`
- `README_CN.md`
- `docs/开发计划.md`

其中：

- `README.md` / `README_CN.md` 负责项目总体说明、部署与开发入口
- `docs/开发计划.md` 负责 agent mode 的实现进度、阶段状态和后续任务顺序

## 当前项目范围

当前代码已经包含：

- JWT 注册、登录、刷新、登出、当前用户接口
- 同步 HTTP、SSE、WebSocket 三种聊天接口
- 会话持久化、聊天历史、用量统计、消息反馈
- 知识库 CRUD、文档上传/导入/搜索、文档预览、分段查看
- 检索设置、快速检索测试、评测数据集、评测运行、评测结果一键应用
- `openai`、`deepseek`、`local`、`mock`、`jina` 五类模型配置管理
- Agent workspace、运行记录、结构化 artifact 展示、skill 绑定、MCP 管理页面
- MCP 治理能力，包括连接测试、catalog 刷新、恢复摘要、审计事件与批量修复入口
- Managed capability 控制面治理能力，包括 publication 预演、高风险强确认、回滚提示和授权影响面摘要
- Agent runtime 的结构化结果契约：`final_output_text`、`final_output_json`、`artifacts`
- `skills`、`knowledge`、`mcp`、`engineering` 四类 agent tool provider 装配
- `txt`、`md`、`pdf`、`html`、`csv`、`tsv`、`json`、`jsonl`、`yaml`、`xml`、`rtf`、`docx`、`pptx`、`xlsx` 文档解析
- 由 Alembic 统一管理的 PostgreSQL schema，覆盖认证、聊天、知识库、模型、配额、检索评测、全文搜索、分块索引

当前 Docker 部署实际使用的是 PostgreSQL、Redis 和 Qdrant，Elasticsearch 不在现行 compose 编排中。

## 当前状态

agent mode 当前的主线已经不再是继续堆 managed capability、MCP 接通能力或兼容桥接本身。

已经进入维护期的部分包括：

- workspace 与结构化结果面
- skill contract 治理与绑定限制
- MCP 治理、批量恢复、审计历史与 follow-up 编排
- managed subagent 控制面、委派运行时以及 legacy bridge 删除

当前仍在持续推进的部分包括：

- 长链路、恢复路径、hydration、schema shaping 和结果面的边界条件回归
- `README.md`、`README_CN.md`、`docs/开发计划.md` 的持续同步

关于当前实现状态和剩余任务顺序，以 `docs/开发计划.md` 为准。

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

当前本地校验入口：

```bash
make test
make test-agent-runtime
make test-platform
make test-frontend
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
- `AI_RUNTIME_HTTP_ADDR`：Platform 调用 Agent、知识库、模型等 Runtime HTTP 接口时必需
- `AI_RUNTIME_CHAT_TRANSPORT`：Go 平台层可切换 `grpc` 或 `http` 调用聊天能力

## 前端能力

当前 Vue 前端已包含：

- 登录和注册
- 流式聊天工作台
- 历史会话
- 用量与成本统计
- 模型管理
- 知识库列表、新建、编辑、详情、设置、检索测试页面
- Agent 列表、Agent Chat workspace、run detail、run history、扩展绑定、MCP 管理页面
- managed capability 控制面页面，包括 publication 治理、授权影响面和 rollout 历史

前端单独启动方式：

```bash
cd frontend-vue
npm install
npm run dev -- --host 0.0.0.0
```

前端通过 `VITE_API_BASE_URL` 指向后端；如果不配置，默认走相对路径。
生产环境前端发布现在会把静态文件构建到 `frontend-dist/releases/<version>`，并更新 `frontend-dist/current`，由共享的基础设施 nginx 直接托管。

前端基础校验命令：

```bash
cd frontend-vue
npm test
npm run build
```

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
- `GET /api/v1/agents`
- `POST /api/v1/agents`
- `GET /api/v1/agents/runs`
- `GET /api/v1/agents/runs/{run_id}`
- `GET /api/v1/agents/runs/{run_id}/events`
- `POST /api/v1/agents/runs/{run_id}/cancel`
- `POST /api/v1/agents/runs/{run_id}/resume`
- managed capability 管理与授权相关 API
- MCP 治理与批量恢复相关 API
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
- agent runtime orchestration、run events、step/tool tracing
- skill runtime context 组合与 output schema shaping
- MCP server catalog、tool discovery 与 runtime provider 装配
- managed subagent delegation、handoff protocol、governance ledger 与 review result shaping
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

Agent 相关改动当前建议至少执行以下校验：

```bash
.venv/bin/python -m pytest ai_runtime/tests/test_agent_runtime_executor.py \
  ai_runtime/tests/test_agent_runtime_schema_utils.py \
  ai_runtime/tests/test_agent_runtime_summarizer.py \
  ai_runtime/tests/test_agent_runtime_skill_registry.py -q
```

说明：

- Python 回归当前统一建议使用仓库根目录的 `.venv` 作为稳定入口
- 如果只做语法级快速校验，再退回 `python3 -m py_compile`；但涉及 agent runtime 契约和 orchestration 的改动，不应只停留在 `py_compile`

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

## 许可证

本项目采用 Apache License 2.0 许可证。英文正式文本见 [LICENSE](./LICENSE)，中文参考译文见 [LICENSE.zh-CN](./LICENSE.zh-CN)。
