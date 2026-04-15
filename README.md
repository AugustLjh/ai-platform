# AI Platform

English | [简体中文](./README_CN.md)

This repository contains a full-stack AI application platform built around three services:

- `frontend-vue`: Vue 3 frontend
- `platform`: Go API gateway, auth layer, session layer, and proxy
- `ai_runtime`: Python FastAPI + gRPC runtime for chat, knowledge base, and model management

This project is not a claim of completeness. It is an open starting point: imperfect, evolving, and shaped by real tradeoffs. The point of publishing it is not to present a finished answer, but to make the current work visible, usable, and easier for others to inspect, adapt, and continue building.

The main maintained documentation in this repository now includes:

- `README.md`
- `README_CN.md`
- `docs/开发计划.md`

Document ownership is split as follows:

- `README.md` / `README_CN.md` cover project scope, deployment, and development entry points
- `docs/开发计划.md` tracks agent mode implementation progress, milestone status, and next-step ordering

## Current Scope

The current codebase includes:

- JWT login, register, refresh, logout, and current-user APIs
- Chat APIs over sync HTTP, SSE, and WebSocket
- Session persistence, chat history, usage statistics, and message feedback
- Knowledge base CRUD, document upload/import/search, document preview, and segment inspection
- Retrieval settings, retrieval quick test, evaluation datasets, evaluation runs, and applying evaluation configs
- LLM model management for `openai`, `deepseek`, `local`, `mock`, and `jina`
- Agent workspace, run history, structured artifact rendering, skill binding, and MCP management pages
- MCP governance support for connection testing, catalog refresh, recovery summaries, audit events, and bulk remediation
- Managed capability control-plane governance, including publication preview, high-risk confirmation, rollback hints, and authorization impact summaries
- Agent runtime structured result contract with `final_output_text`, `final_output_json`, and `artifacts`
- Agent tool provider bootstrapping for `skills`, `knowledge`, `mcp`, and `engineering`
- File parsing for `txt`, `md`, `pdf`, `html`, `csv`, `tsv`, `json`, `jsonl`, `yaml`, `xml`, `rtf`, `docx`, `pptx`, and `xlsx`
- Alembic-managed PostgreSQL schema for auth, chat data, knowledge bases, model config, quotas, retrieval evaluation, full-text search, and chunk indexing

The current Docker deployment uses PostgreSQL, Redis, and Qdrant. Elasticsearch is not part of the active compose stack.

## Current Status

The agent-mode mainline is no longer centered on building out managed capabilities, MCP plumbing, or legacy compatibility bridges.

What is already in maintenance mode:

- workspace and structured result surfaces
- skill contract governance and binding restrictions
- MCP governance, bulk remediation, audit history, and follow-up orchestration
- managed subagent control plane, delegation runtime, and legacy bridge removal

What is still actively being pushed:

- broader regression coverage for long chains, recovery paths, hydration, schema shaping, and result-surface edge cases
- ongoing synchronization across `README.md`, `README_CN.md`, and `docs/开发计划.md`

For the current implementation status and remaining work ordering, use `docs/开发计划.md` as the source of truth.

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
  |- rate limit / guard / cost tracking
  |- chat session APIs
  |- reverse proxy for knowledge-base and model APIs
  |
  +--> Python AI runtime HTTP (:8000)
  |      |- FastAPI docs
  |      |- knowledge base / documents / models
  |      |- optional HTTP chat endpoint
  |
  +--> Python AI runtime gRPC (:50051)
         |- streaming chat backend

PostgreSQL + Qdrant
Redis
```

## Project Layout

```text
.
|-- ai_runtime/              # Python runtime service
|-- db/alembic/             # Alembic migrations
|-- frontend-vue/            # Vue 3 frontend
|-- nginx/                   # Nginx gateway config
|-- platform/                # Go platform service
|-- proto/                   # Shared proto definitions
|-- scripts/                 # Helper scripts
|-- docker-compose.infra.yml
|-- docker-compose.backend.yml
|-- docker-compose.frontend.yml
|-- Makefile                 # Main entry for local operations
|-- README.md
`-- README_CN.md
```

## Quick Start

### Prerequisites

- Docker Engine with Compose plugin
- GNU Make
- Git

### Local Development

Development now runs directly from each service directory. The repository no longer keeps a separate Docker Compose-based dev stack.

Common local commands:

```bash
cd frontend-vue && npm install && npm run dev -- --host 0.0.0.0
cd platform && go run main.go
cd ai_runtime && pip install -r requirements.txt && python -m main --mode both --http-port 8000 --grpc-port 50051
make test
```

Current local verification entry points:

```bash
make test
make test-agent-runtime
make test-platform
make test-frontend
```

### Unified Deployment

The project now keeps only the split deployment compose files:

- `docker-compose.infra.yml`
- `docker-compose.backend.yml`
- `docker-compose.frontend.yml` for frontend build-only publishing

Recommended sequence for a fresh environment:

```bash
make infra-up
make db-upgrade
make backend-up
make frontend-build
```

If images already exist locally and you want the guarded one-shot startup:

```bash
make prod-check
make prod
```

Rebuild commands:

```bash
make infra-build
make backend-build
make frontend-build
```

Low-I/O rebuild commands:

```bash
make infra-build-safe
make ai-runtime-build-safe
make platform-build-safe
make frontend-build-safe
```

Operational helpers:

```bash
make infra-logs
make backend-logs
make frontend-logs
make prod-down
```

Database helpers:

```bash
make db-upgrade
make db-current
make db-history
make db-revision m=add_some_change
```

## Environment Files

The repository uses three main env files:

- `./.env.example`: shared deployment variables such as `JWT_SECRET`, database access, domain, and SSL settings
- `./ai_runtime/.env.example`: AI runtime settings such as embedding provider, quota, RAG, and runtime ports
- `./platform/.env.example`: Go platform settings such as runtime addresses and JWT secret

Copy the examples before local deployment if your environment differs from the repository defaults.

Important current settings:

- `JWT_SECRET` must be replaced in production
- `EMBEDDING_PROVIDER` supports `local`, `openai`, and `jina`
- `LLM_PROVIDER` supports `openai`, `deepseek`, `local`, and `mock`
- `QDRANT_HOST` / `QDRANT_PORT` point the runtime to the dedicated vector database
- `AI_RUNTIME_HTTP_ADDR` is required for agent, knowledge-base, and model APIs on the Go platform
- `AI_RUNTIME_CHAT_TRANSPORT` on the Go service can switch chat calls between `grpc` and `http`

## Frontend Capabilities

The Vue frontend currently exposes:

- login and registration
- chat workspace with streaming responses
- chat history
- usage and cost statistics
- model management
- knowledge base list, create, edit, settings, detail, and retrieval-test pages
- agent list, agent chat workspace, run detail, run history, extension binding, and MCP management pages
- managed capability control-plane pages for publication governance, authorization impact, and rollout history

Frontend local run:

```bash
cd frontend-vue
npm install
npm run dev -- --host 0.0.0.0
```

The frontend uses `VITE_API_BASE_URL`, defaulting to relative paths when unset.
Production-style frontend publishing now builds static assets into `frontend-dist/releases/<version>` and updates `frontend-dist/current`, which the shared infra nginx serves directly.

Baseline frontend verification:

```bash
cd frontend-vue
npm test
npm run build
```

## Platform Service

The Go platform is the user-facing backend. It provides:

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
- managed capability admin and authorization APIs
- MCP governance and bulk-remediation APIs
- `GET /api/v1/chat/sessions`
- `GET /api/v1/chat/history/{session_id}`
- `GET /api/v1/chat/usage/stats`
- `GET /api/v1/chat/feedback/low-quality`
- `POST /api/v1/chat/messages/{id}/feedback`
- proxied `/api/v1/knowledge-bases/*`
- proxied `/api/v1/knowledge/*`
- proxied `/api/v1/models/*`

Platform local run:

```bash
cd platform
go run main.go
```

## AI Runtime

The Python runtime runs both HTTP and gRPC servers and owns the AI/domain logic.

Main responsibilities:

- chat generation
- agent runtime orchestration, run events, and step/tool tracing
- skill runtime-context composition and output-schema shaping
- MCP server catalog, tool discovery, and runtime provider bootstrap
- managed subagent delegation, handoff protocol, governance ledger, and review-result shaping
- knowledge base management
- document parsing, chunking, and search
- retrieval evaluation
- LLM model storage and selection

Runtime local run:

```bash
cd ai_runtime
pip install -r requirements.txt
python -m main --mode both --http-port 8000 --grpc-port 50051
```

FastAPI docs:

- `http://localhost:8000/docs`

For agent-related code changes, the recommended verification path is:

```bash
.venv/bin/python -m pytest ai_runtime/tests/test_agent_runtime_executor.py \
  ai_runtime/tests/test_agent_runtime_schema_utils.py \
  ai_runtime/tests/test_agent_runtime_summarizer.py \
  ai_runtime/tests/test_agent_runtime_skill_registry.py -q
```

Notes:

- use the repository-root `.venv` as the stable Python test entrypoint for runtime changes
- `python3 -m py_compile` is still acceptable for syntax-only smoke checks, but agent-runtime contract or orchestration changes should not stop there

## Database and Migrations

The database is now managed only through Alembic under `db/alembic/`.

Apply the latest schema with:

```bash
make db-upgrade
```

Create a new revision with:

```bash
make db-revision m=describe_change
```

To preserve existing data while resetting the database onto the Alembic baseline:

```bash
make db-reset-to-alembic
```

If you restore existing knowledge-base data onto a fresh deployment, rebuild the native Qdrant index with:

```bash
make qdrant-backfill
```

Current data services in active deployment:

- PostgreSQL
- Redis
- Qdrant

## Demo Account

The Go platform seeds a demo user at startup:

```text
Email: demo@example.com
Password: demo123456
```

## Notes

- `make prod` is the umbrella alias for the current split deployment flow.
- `make frontend-build` publishes static assets only. There is no dedicated production frontend container anymore.
- `FRONTEND_NODE_IMAGE` defaults to the official `node:20-alpine`. Override it only if you need a different internal mirror.
- If `ai_runtime/.env` sets `EMBEDDING_PROVIDER=local`, `make prod-check` will block startup unless `ALLOW_LOCAL_EMBEDDING=1` is provided.
- Some helper scripts under `scripts/` still use `docker-compose` syntax and should be treated as legacy helpers compared with the current `Makefile`.

## License

This project is licensed under the Apache License 2.0. See [LICENSE](./LICENSE) for the official license text and [LICENSE.zh-CN](./LICENSE.zh-CN) for a Chinese reference translation.
