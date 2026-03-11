# AI Platform

English | [简体中文](./README_CN.md)

This repository contains a full-stack AI application platform built around three services:

- `frontend-vue`: Vue 3 frontend
- `platform`: Go API gateway, auth layer, session layer, and proxy
- `ai_runtime`: Python FastAPI + gRPC runtime for chat, knowledge base, and model management

This repository now keeps only two maintained documentation files:

- `README.md`
- `README_CN.md`

If you add or change documentation, update these two files only.

## Current Scope

The current codebase includes:

- JWT login, register, refresh, logout, and current-user APIs
- Chat APIs over sync HTTP, SSE, and WebSocket
- Session persistence, chat history, usage statistics, and message feedback
- Knowledge base CRUD, document upload/import/search, document preview, and segment inspection
- Retrieval settings, retrieval quick test, evaluation datasets, evaluation runs, and applying evaluation configs
- LLM model management for `openai`, `deepseek`, `local`, `mock`, and `jina`
- File parsing for `txt`, `md`, `pdf`, `html`, `csv`, `tsv`, `json`, `jsonl`, `yaml`, `xml`, `rtf`, `docx`, `pptx`, and `xlsx`
- PostgreSQL migrations for auth, chat data, knowledge bases, model config, quotas, retrieval evaluation, full-text search, and chunk indexing

The current Docker deployment uses PostgreSQL and Redis. Elasticsearch is not part of the active compose stack.

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

PostgreSQL + pgvector
Redis
```

## Project Layout

```text
.
|-- ai_runtime/              # Python runtime service
|-- db/migrations/           # SQL migrations
|-- frontend-vue/            # Vue 3 frontend
|-- nginx/                   # Nginx gateway config
|-- platform/                # Go platform service
|-- proto/                   # Shared proto definitions
|-- scripts/                 # Helper scripts
|-- docker-compose*.yml      # Dev and split production compose files
|-- Makefile                 # Main entry for local operations
|-- README.md
`-- README_CN.md
```

## Quick Start

### Prerequisites

- Docker Engine with Compose plugin
- GNU Make
- Git

### Development

The default development path is the hot-reload stack:

```bash
make dev
```

Main endpoints after startup:

- Frontend: `http://localhost:5173`
- Platform API: `http://localhost:8080`
- AI Runtime HTTP: `http://localhost:8000`
- PostgreSQL: `localhost:5433`
- Redis: `localhost:6379`

Useful commands:

```bash
make dev-logs
make dev-down
make test
```

### Production-style Split Deployment

The project is currently organized around split compose files:

- `docker-compose.infra.yml`
- `docker-compose.backend.yml`
- `docker-compose.frontend.yml`

Recommended sequence for a fresh environment:

```bash
make infra-up
make db-migrate
make backend-up
make frontend-up
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
- `AI_RUNTIME_CHAT_TRANSPORT` on the Go service can switch chat calls between `grpc` and `http`

## Frontend Capabilities

The Vue frontend currently exposes:

- login and registration
- chat workspace with streaming responses
- chat history
- usage and cost statistics
- model management
- knowledge base list, create, edit, settings, detail, and retrieval-test pages

Frontend local run:

```bash
cd frontend-vue
npm install
npm run dev -- --host 0.0.0.0
```

The frontend uses `VITE_API_BASE_URL`, defaulting to relative paths when unset.

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

## Database and Migrations

Migrations live under `db/migrations/` and currently include:

- base schema
- knowledge-base enhancements
- pgvector enablement
- knowledge-base tables
- document migration
- LLM model tables and model types
- quota periods
- retrieval evaluation
- full-text search
- document chunk indexing

Run all current migrations with:

```bash
make db-migrate
```

Current data services in active deployment:

- PostgreSQL
- Redis

## Demo Account

The Go platform seeds a demo user at startup:

```text
Email: demo@example.com
Password: demo123456
```

## Notes

- `make prod` intentionally refuses implicit image builds.
- If `ai_runtime/.env` sets `EMBEDDING_PROVIDER=local`, `make prod-check` will block startup unless `ALLOW_LOCAL_EMBEDDING=1` is provided.
- Some helper scripts under `scripts/` still use `docker-compose` syntax and should be treated as legacy helpers compared with the current `Makefile`.
