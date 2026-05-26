# AI Platform

English | [简体中文](./README_CN.md)

AI Platform is a full-stack application platform for chat, knowledge base workflows, and agent runtime orchestration.

## Services

- `frontend-vue`: Vue 3 frontend
- `platform`: Go API gateway, auth layer, session layer, and runtime proxy
- `ai_runtime`: Python FastAPI + gRPC runtime for chat, knowledge base, models, and agent execution

## Current Status

The repository is active and already includes a usable mainline for:

- user auth, chat, session history, usage stats, and feedback
- knowledge base CRUD, document upload/import/search, preview, chunk inspection, and retrieval testing
- model configuration for `openai`, `deepseek`, `jina`, `qwen`, `wenxin`, `glm`, `kimi`, `doubao`, `local`, and `mock`
- agent workspace, run history, structured artifacts, run tree, MCP management, and subagent governance pages
- agent runtime result contracts, tool/provider bootstrap, MCP integration, skill binding, review flow, and delegation governance
- PostgreSQL schema management with Alembic
- deployment around PostgreSQL, Redis, and Qdrant

## Architecture

```text
Browser
  |
  v
Vue 3 frontend
  |
  v
Go platform (:8080)
  |- JWT auth
  |- chat/session APIs
  |- usage and feedback APIs
  |- agent APIs and governance endpoints
  |- proxy for knowledge base and model APIs
  |
  +--> Python AI runtime HTTP (:8000)
  |      |- knowledge base / documents / models
  |      |- optional HTTP chat endpoint
  |      |- agent runtime APIs
  |
  +--> Python AI runtime gRPC (:50051)
         |- streaming chat backend

PostgreSQL + Redis + Qdrant
```

## Project Layout

```text
.
|-- ai_runtime/               # Python runtime service
|-- db/alembic/               # Alembic migrations
|-- frontend-vue/             # Vue 3 frontend
|-- frontend-dist/            # Published frontend static releases
|-- nginx/                    # Nginx config
|-- platform/                 # Go platform service
|-- proto/                    # Shared proto definitions
|-- scripts/                  # Helper scripts
|-- docker-compose.infra.yml
|-- docker-compose.backend.yml
|-- docker-compose.frontend.yml
|-- Makefile
|-- README.md
`-- README_CN.md
```

## Requirements

- Docker Engine with Compose plugin
- GNU Make
- Git
- Node.js 20+ for local frontend work
- Go 1.24+ for local platform work
- Python 3.11+ for local runtime work

## Local Development

Run each service from its own directory.

Frontend:

```bash
cd frontend-vue
npm install
npm run dev -- --host 0.0.0.0
```

Platform:

```bash
cd platform
go run main.go
```

AI Runtime:

```bash
pip install -r ai_runtime/requirements.txt
python -m ai_runtime.main --mode both --http-port 8000 --grpc-port 50051
```

Common local verification:

```bash
make test
make test-agent-runtime
make test-platform
make test-frontend
```

## Deployment

The repository uses split compose files:

- `docker-compose.infra.yml`
- `docker-compose.backend.yml`
- `docker-compose.frontend.yml`

Recommended startup sequence:

```bash
make infra-up
make db-upgrade
make backend-up
make frontend-build
```

If all required images are already present locally:

```bash
make prod-check
make prod
```

Build and publish helpers:

```bash
make infra-build
make backend-build
make frontend-build
```

Low-I/O variants:

```bash
make infra-build-safe
make ai-runtime-build-safe
make platform-build-safe
make frontend-build-safe
```

Operations:

```bash
make infra-logs
make backend-logs
make frontend-logs
make prod-down
```

## Environment Files

Main templates:

- `./.env.example`
- `./ai_runtime/.env.example` (runtime models, embedding, rag, qdrant)
- `./platform/.env.example`

Important settings:

- `JWT_SECRET`: must be replaced in production
- `EMBEDDING_PROVIDER`: see `./ai_runtime/.env.example`
- `LLM_PROVIDER`: see `./ai_runtime/.env.example`
- `QDRANT_HOST` / `QDRANT_PORT`: see `./ai_runtime/.env.example`
- `AI_RUNTIME_HTTP_ADDR`: required for platform access to runtime HTTP APIs
- `AI_RUNTIME_CHAT_TRANSPORT`: selects `grpc` or `http` for chat transport on the Go service

## Frontend

The current frontend includes:

- login and registration
- chat workspace and session history
- usage and cost statistics
- model management
- knowledge base list, create, edit, detail, settings, and retrieval test pages
- agent list, agent chat workspace, run history, run detail, extension binding, MCP management, and subagent management pages

Production frontend publishing writes static assets into `frontend-dist/releases/<version>` and updates `frontend-dist/current`.

## Platform

The Go platform is the user-facing backend. It provides auth, chat/session APIs, agent APIs, usage and feedback endpoints, and proxies runtime knowledge-base/model APIs.

Local run:

```bash
cd platform
go run main.go
```

The platform seeds a demo user at startup:

```text
Email: demo@example.com
Password: demo123456
```

## AI Runtime

The Python runtime owns AI-side execution and serves both HTTP and gRPC.

Main responsibilities:

- chat generation
- agent runtime orchestration, events, and tracing
- skill loading and tool/provider bootstrap
- MCP catalog, discovery, sessions, and runtime integration
- subagent delegation, review flow, and governance state
- knowledge base management
- document parsing, chunking, retrieval, and evaluation
- model storage and selection

Recommended targeted verification for agent-runtime changes:

```bash
.venv/bin/python -m pytest ai_runtime/tests/test_agent_runtime_executor.py \
  ai_runtime/tests/test_agent_runtime_schema_utils.py \
  ai_runtime/tests/test_agent_runtime_summarizer.py \
  ai_runtime/tests/test_agent_runtime_skill_registry.py -q
```

## Database

Database schema is managed through Alembic in `db/alembic/`.

Common commands:

```bash
make db-upgrade
make db-current
make db-history
make db-revision m=describe_change
make db-reset-to-alembic
make qdrant-backfill
```

## License

This project is licensed under the Apache License 2.0. See [LICENSE](./LICENSE) and [LICENSE.zh-CN](./LICENSE.zh-CN).
