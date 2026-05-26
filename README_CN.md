# AI Platform

[English](./README.md) | 简体中文

AI Platform 是一个面向聊天、知识库和 Agent Runtime 编排的全栈应用平台。

## 服务组成

- `frontend-vue`：Vue 3 前端
- `platform`：Go 平台层，负责认证、会话、对外 API 和 Runtime 代理
- `ai_runtime`：Python FastAPI + gRPC 运行时，负责聊天、知识库、模型和 Agent 执行

## 当前状态

当前仓库已经具备可直接使用的主线能力：

- 用户认证、聊天、会话历史、用量统计和消息反馈
- 知识库 CRUD、文档上传/导入/搜索、预览、分块查看和检索测试
- `openai`、`deepseek`、`jina`、`qwen`、`wenxin`、`glm`、`kimi`、`doubao`、`local`、`mock` 模型配置管理
- Agent 工作台、运行历史、结构化产物展示、运行树、MCP 管理和子代理治理页面
- Agent Runtime 结果契约、工具与 provider 装配、MCP 集成、技能绑定、评审流程和委派治理
- 基于 Alembic 的 PostgreSQL schema 管理
- 围绕 PostgreSQL、Redis、Qdrant 的部署方式

## 架构

```text
浏览器
  |
  v
Vue 3 前端
  |
  v
Go 平台层 (:8080)
  |- JWT 认证
  |- 聊天与会话接口
  |- 用量与反馈接口
  |- Agent 接口与治理接口
  |- 知识库和模型接口代理
  |
  +--> Python AI Runtime HTTP (:8000)
  |      |- 知识库 / 文档 / 模型接口
  |      |- 可选 HTTP 聊天接口
  |      |- Agent Runtime 接口
  |
  +--> Python AI Runtime gRPC (:50051)
         |- 流式聊天后端

PostgreSQL + Redis + Qdrant
```

## 项目结构

```text
.
|-- ai_runtime/               # Python Runtime 服务
|-- db/alembic/               # Alembic 迁移
|-- frontend-vue/             # Vue 3 前端
|-- frontend-dist/            # 前端静态发布目录
|-- nginx/                    # Nginx 配置
|-- platform/                 # Go 平台层
|-- proto/                    # 共享 proto 定义
|-- scripts/                  # 辅助脚本
|-- docker-compose.infra.yml
|-- docker-compose.backend.yml
|-- docker-compose.frontend.yml
|-- Makefile
|-- README.md
`-- README_CN.md
```

## 环境要求

- Docker Engine 和 Compose 插件
- GNU Make
- Git
- Node.js 20+，用于本地前端开发
- Go 1.24+，用于本地平台层开发
- Python 3.11+，用于本地 Runtime 开发

## 本地开发

当前采用各服务目录独立启动。

前端：

```bash
cd frontend-vue
npm install
npm run dev -- --host 0.0.0.0
```

平台层：

```bash
cd platform
go run main.go
```

AI Runtime：

```bash
pip install -r ai_runtime/requirements.txt
python -m ai_runtime.main --mode both --http-port 8000 --grpc-port 50051
```

常用本地校验：

```bash
make test
make test-agent-runtime
make test-platform
make test-frontend
```

## 部署

当前仓库使用拆分后的 compose 文件：

- `docker-compose.infra.yml`
- `docker-compose.backend.yml`
- `docker-compose.frontend.yml`

推荐启动顺序：

```bash
make infra-up
make db-upgrade
make backend-up
make frontend-build
```

如果本地镜像已经准备好：

```bash
make prod-check
make prod
```

构建与发布：

```bash
make infra-build
make backend-build
make frontend-build
```

低 I/O 版本：

```bash
make infra-build-safe
make ai-runtime-build-safe
make platform-build-safe
make frontend-build-safe
```

运维入口：

```bash
make infra-logs
make backend-logs
make frontend-logs
make prod-down
```

## 环境变量文件

主要模板文件：

- `./.env.example`
- `./ai_runtime/.env.example`（runtime 模型、Embedding、RAG、Qdrant 配置）
- `./platform/.env.example`

关键配置：

- `JWT_SECRET`：生产环境必须替换
- `EMBEDDING_PROVIDER`：见 `./ai_runtime/.env.example`
- `LLM_PROVIDER`：见 `./ai_runtime/.env.example`
- `QDRANT_HOST` / `QDRANT_PORT`：见 `./ai_runtime/.env.example`
- `AI_RUNTIME_HTTP_ADDR`：Platform 访问 Runtime HTTP 接口所需地址
- `AI_RUNTIME_CHAT_TRANSPORT`：Go 服务使用 `grpc` 或 `http` 调用聊天能力

## 前端

当前前端已包含：

- 登录和注册
- 聊天工作台和会话历史
- 用量与成本统计
- 模型管理
- 知识库列表、新建、编辑、详情、设置和检索测试页面
- Agent 列表、Agent Chat 工作台、运行历史、运行详情、扩展绑定、MCP 管理和子代理管理页面

生产发布时，前端静态资源会写入 `frontend-dist/releases/<version>`，并更新 `frontend-dist/current`。

## Platform

Go 平台层是用户直接访问的后端，负责认证、聊天与会话接口、Agent 接口、用量与反馈接口，以及 Runtime 的知识库和模型代理。

本地启动：

```bash
cd platform
go run main.go
```

平台层启动时会写入一个演示账号：

```text
Email: demo@example.com
Password: demo123456
```

## AI Runtime

Python Runtime 负责 AI 侧执行逻辑，同时提供 HTTP 和 gRPC 服务。

主要职责：

- 聊天生成
- Agent Runtime 编排、事件流和追踪
- 技能加载与工具/provider 装配
- MCP catalog、发现、会话和运行时集成
- 子代理委派、评审流程和治理状态
- 知识库管理
- 文档解析、切分、检索和评测
- 模型存储与选择

Agent Runtime 相关改动建议至少执行以下校验：

```bash
.venv/bin/python -m pytest ai_runtime/tests/test_agent_runtime_executor.py \
  ai_runtime/tests/test_agent_runtime_schema_utils.py \
  ai_runtime/tests/test_agent_runtime_summarizer.py \
  ai_runtime/tests/test_agent_runtime_skill_registry.py -q
```

## 数据库

数据库 schema 通过 `db/alembic/` 下的 Alembic 管理。

常用命令：

```bash
make db-upgrade
make db-current
make db-history
make db-revision m=describe_change
make db-reset-to-alembic
make qdrant-backfill
```

## 许可证

本项目采用 Apache License 2.0。见 [LICENSE](./LICENSE) 和 [LICENSE.zh-CN](./LICENSE.zh-CN)。
