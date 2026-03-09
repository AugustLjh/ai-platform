# AI Platform - Enterprise AI Application Platform

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Go Version](https://img.shields.io/badge/Go-1.21+-00ADD8?logo=go)](https://golang.org/)
[![Python Version](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python)](https://www.python.org/)

A production-ready AI application platform with microservices architecture using Go (Platform Layer) and Python (AI Runtime), communicating via gRPC streaming.

English | [简体中文](./README_CN.md)

## 🌟 Key Features

### Frontend (Vue 3)
- ✅ **Modern Interface** - Clean and responsive design
- ✅ **Real-time Chat** - Streaming responses with SSE
- ✅ **Knowledge Base** - Document upload, search, management
- ✅ **Session Management** - Multiple chat sessions
- ✅ **Mobile Friendly** - Works on all devices

### Platform Layer (Go)
- ✅ **JWT Authentication** - Complete user registration/login system
- ✅ **Multi-Tenancy** - Tenant isolation and management
- ✅ **Rate Limiting** - Token bucket algorithm
- ✅ **Content Security** - Request filtering and safety checks
- ✅ **Cost Tracking** - Token usage metering and cost calculation
- ✅ **Multi-Protocol** - HTTP/SSE/WebSocket support
- ✅ **API Proxy** - Knowledge base API reverse proxy

### AI Runtime (Python)
- ✅ **Knowledge Base** - Document management, vector search
- ✅ **RAG Pipeline** - Retrieval-Augmented Generation
- ✅ **LLM Integration** - OpenAI and local model support
- ✅ **Agent System** - Tool-using agents
- ✅ **Streaming** - Complete streaming output support
- ✅ **File Parsing** - PDF, Markdown, HTML support

### Databases
- ✅ **PostgreSQL + pgvector** - Users, sessions, documents, vectors
- ✅ **Redis** - Cache, token blacklist, rate limiting
- ✅ **Elasticsearch** - Full-text search, logging

## 📋 Table of Contents

- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Development](#development)
- [Production Deployment](#production-deployment)
- [API Documentation](#api-documentation)
- [Configuration](#configuration)

---

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose
- Git

### Development Environment (Hot Reload)

```bash
# Clone the repository
git clone <repository-url>
cd ai-platform

# Start development environment
make dev

# Or use docker-compose
docker-compose -f docker-compose.yml -f docker-compose.dev.yml --profile full up -d
```

For split orchestration, see [docs/DOCKER_COMPOSE_SPLIT.md](/mnt/ai-platform/docs/DOCKER_COMPOSE_SPLIT.md).

**Access URLs:**
- Frontend (Vite dev server): http://localhost:5173
- Backend API: http://localhost:8080
- AI Runtime: http://localhost:8000
- PostgreSQL: localhost:5433
- Redis: localhost:6379
- Elasticsearch: http://localhost:9200

**Development Features:**
- ✅ Hot reload (Python watchdog, Go Air, Vite HMR)
- ✅ Source code mounted to containers
- ✅ All ports exposed for debugging
- ✅ Detailed debug logs

### Production Environment (Fully Containerized)

```bash
# Start production environment
make prod

# Or use docker-compose
docker-compose -f docker-compose.yml -f docker-compose.prod.yml --profile full up -d
```

If you need to rebuild infra, backend, and frontend independently, use the split files documented in
[docs/DOCKER_COMPOSE_SPLIT.md](/mnt/ai-platform/docs/DOCKER_COMPOSE_SPLIT.md).

**Access URLs:**
- HTTP: http://localhost
- HTTPS: https://your-domain.com (requires domain and certificate)

**Production Features:**
- ✅ Fully containerized, no host dependencies
- ✅ Optimized resource limits
- ✅ Health checks and auto-restart
- ✅ Only necessary ports exposed (80/443)

### Demo Account

```
Email: demo@example.com
Password: demo123456
```

---

## 🏗️ Architecture

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
│  - UI           │            │  - JWT Auth     │
│  - Knowledge    │            │  - Rate Limit   │
│  - Chat         │            │  - Cost Track   │
└─────────────────┘            │  - API Proxy    │
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
                        │  - LLM Integration  │
                        │  - RAG Pipeline     │
                        │  - Vector Search    │
                        │  - File Parsing     │
                        └──────────┬──────────┘
                                   │
                ┌──────────────────┼──────────────────┐
                ▼                  ▼                  ▼
        ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
        │ PostgreSQL   │  │    Redis     │  │Elasticsearch │
        │  + pgvector  │  │              │  │              │
        └──────────────┘  └──────────────┘  └──────────────┘
```

### Communication Flow

1. **Authentication**: User → Nginx → Platform (JWT) → Return Token
2. **Chat**: User → Nginx → Platform → AI Runtime (gRPC) → LLM → Stream Response
3. **Knowledge Base**: User → Nginx → Platform (HTTP Proxy) → AI Runtime → PostgreSQL

---

## 📁 Project Structure

```
ai-platform/
├── frontend-vue/              # Vue 3 Frontend
│   ├── src/
│   │   ├── api/              # API calls
│   │   ├── components/       # Reusable components
│   │   ├── views/            # Page views
│   │   ├── store/            # Pinia state management
│   │   └── router/           # Vue Router
│   ├── Dockerfile            # Production build
│   └── Dockerfile.dev        # Development build
│
├── platform/                  # Go Platform Layer
│   ├── main.go               # Main entry
│   ├── api/
│   │   ├── http/             # HTTP handlers
│   │   └── grpc/             # gRPC client
│   ├── middleware/           # Middleware
│   ├── auth/                 # Auth service
│   ├── service/              # Business logic
│   ├── proto/chat/           # Protobuf generated files
│   ├── Dockerfile            # Production build
│   └── .air.toml             # Hot reload config
│
├── ai_runtime/                # Python AI Runtime
│   ├── main.py               # Main entry
│   ├── api/
│   │   ├── http_server.py    # FastAPI HTTP service
│   │   ├── grpc_server.py    # gRPC service
│   │   ├── chat_service.py   # Chat service
│   │   └── knowledge_base.py # Knowledge base API
│   ├── core/
│   │   ├── services/         # Business logic
│   │   ├── repositories/     # Data access
│   │   ├── models/           # Data models
│   │   ├── embeddings/       # Vector embeddings
│   │   └── parsers/          # File parsers
│   ├── Dockerfile            # Production build
│   └── requirements.txt      # Python dependencies
│
├── nginx/                     # Nginx Gateway
│   ├── Dockerfile
│   ├── nginx.conf
│   └── conf.d/
│
├── db/migrations/             # Database migrations
│   ├── 001_initial_schema.sql
│   ├── 002_knowledge_base_enhancements.sql
│   └── 003_enable_pgvector.sql
│
├── proto/                     # Protobuf definitions
│   └── chat_service.proto
│
├── docker-compose.yml         # Base configuration
├── docker-compose.dev.yml     # Development config
├── docker-compose.prod.yml    # Production config
├── docker-compose.infra.yml   # Split infra orchestration
├── docker-compose.backend.yml # Split backend orchestration
├── docker-compose.frontend.yml# Split frontend orchestration
├── Makefile                   # Convenient commands
├── .env                       # Environment variables
└── README.md                  # This document
```

---

## 💻 Development

### Start Development Environment

```bash
# Using Makefile (recommended)
make dev

# View logs
make dev-logs

# Stop
make dev-down
```

### Development Features

**Hot Reload:**
- **Python**: watchdog auto-restart
- **Go**: Air hot reload
- **Vue**: Vite HMR

**Source Code Mounting:**
```yaml
ai-runtime:
  volumes:
    - ./ai_runtime:/app:rw              # Mount source code
    - huggingface_cache:/root/.cache    # Cache persistence

platform:
  volumes:
    - ./platform:/src/platform:rw       # Mount source code
    - platform_build_cache:/go/pkg      # Go build cache

frontend:
  volumes:
    - ./frontend-vue:/app:rw            # Mount source code
    - /app/node_modules                 # Exclude node_modules
```

### Code Changes

1. Modify Python code → Auto-restart AI Runtime
2. Modify Go code → Air auto-recompile
3. Modify Vue code → Vite HMR instant update

### Debugging

```bash
# View specific service logs
docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f platform
docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f ai-runtime
docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f frontend

# Enter container
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec platform sh
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec ai-runtime bash

# Connect to database
make db-shell

# Connect to Redis
make redis-cli
```

---

## 🚢 Production Deployment

### Start Production Environment

```bash
# Recommended: start the split layers separately
make infra-up
make backend-up
make frontend-up

# View logs
make infra-logs
make backend-logs
make frontend-logs

# Stop
make frontend-down
make backend-down
make infra-down
```

The compatibility stack commands are still available:

```bash
make prod
make prod-build
make prod-down
```

### Production Features

**Fully Containerized:**
- ❌ No source code mounting
- ✅ Use code copied during build
- ✅ Containers run independently

**Resource Limits:**
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

**Health Checks:**
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 40s
```

**Auto Restart:**
```yaml
restart: always
```

### Configure Domain and SSL

1. Modify `.env` file:
```bash
DOMAIN=your-domain.com
EMAIL=admin@your-domain.com
LETSENCRYPT_STAGING=0
```

2. Restart Nginx:
```bash
docker-compose restart nginx
```

3. Obtain SSL certificate:
```bash
docker-compose exec certbot certbot certonly \
  --webroot -w /var/www/certbot \
  -d your-domain.com \
  --email admin@your-domain.com \
  --agree-tos
```

---

## 📚 API Documentation

### Authentication API

**Register**
```http
POST /api/v1/auth/register
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "password123"
}
```

**Login**
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

**Get Current User**
```http
GET /api/v1/auth/me
Authorization: Bearer <access_token>
```

### Chat API

**Synchronous Chat**
```http
POST /api/v1/chat
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "session_id": "session-123",
  "message": "Hello",
  "config": {
    "use_rag": false,
    "use_agent": false,
    "temperature": 0.7,
    "max_tokens": 2000
  }
}
```

**Streaming Chat (SSE)**
```http
POST /api/v1/chat/sse
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "session_id": "session-123",
  "message": "Hello"
}

Response: (Server-Sent Events)
data: {"type": 1, "content": "Hel"}
data: {"type": 1, "content": "lo"}
data: [DONE]
```

### Knowledge Base API

**List Documents**
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

**Create Document**
```http
POST /api/v1/knowledge/documents
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "title": "Document Title",
  "content": "Document content",
  "source": "manual",
  "source_type": "manual",
  "access_level": "tenant",
  "auto_index": true
}
```

**Upload File**
```http
POST /api/v1/knowledge/documents/upload
Authorization: Bearer <access_token>
Content-Type: multipart/form-data

file: <file>
access_level: tenant
auto_index: true
```

**Search Documents**
```http
POST /api/v1/knowledge/documents/search
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "query": "search keywords",
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

**Get Statistics**
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

## ⚙️ Configuration

### Environment Variables

**Root `.env`**
```bash
# JWT Secret
JWT_SECRET=your-secret-key-change-this-in-production

# Database Configuration
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

# Domain Configuration (Production)
DOMAIN=your-domain.com
EMAIL=admin@your-domain.com
```

**ai_runtime/.env**
```bash
# Embedding Model Configuration
EMBEDDING_PROVIDER=local
EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2
EMBEDDING_DEVICE=cpu

# LLM Configuration
LLM_PROVIDER=openai
OPENAI_API_KEY=your-api-key
OPENAI_API_BASE=https://api.openai.com/v1

# RAG Configuration
ENABLE_RAG=true
RAG_TOP_K=5
RAG_SIMILARITY_THRESHOLD=0.7

# Agent Configuration
ENABLE_AGENT=true
AGENT_MAX_ITERATIONS=10
```

### Makefile Commands

```bash
# View all commands
make help

# Development
make dev              # Start development environment
make dev-build        # Rebuild and start
make dev-logs         # View logs
make dev-down         # Stop

# Production
make infra-up         # Start infra
make backend-up       # Start backend
make frontend-up      # Start frontend
make infra-build      # Rebuild infra images
make backend-build    # Rebuild backend images
make frontend-build   # Rebuild frontend images
make infra-logs       # View infra logs
make backend-logs     # View backend logs
make frontend-logs    # View frontend logs
make prod             # Compatibility full-stack start
make prod-build       # Compatibility full-stack rebuild
make prod-down        # Compatibility full-stack stop

# Database Management
make db-migrate       # Run database migrations
make db-shell         # Connect to PostgreSQL
make redis-cli        # Connect to Redis

# Service Management
make restart-platform
make restart-ai-runtime
make restart-frontend
```

---

## 🔧 Troubleshooting

### View Logs

```bash
# Full development logs
make dev-logs

# Split production logs
make infra-logs
make backend-logs
make frontend-logs
```

### Enter Container

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec platform sh
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec ai-runtime bash
docker compose -f docker-compose.infra.yml exec postgres psql -U ai_platform -d ai_platform
```

### Restart Service

```bash
make restart-platform
make restart-ai-runtime
make restart-frontend
make restart-nginx
```

### Clean and Rebuild

```bash
make clean
make dev-build
```

---

## 📝 FAQ

**Q: How to switch LLM provider?**

A: Modify `LLM_PROVIDER` and related configs in `ai_runtime/.env`.

**Q: How to add new embedding model?**

A: Modify `EMBEDDING_PROVIDER` and `EMBEDDING_MODEL` in `ai_runtime/.env`.

**Q: How to backup data?**

A:
```bash
# Backup PostgreSQL
docker-compose exec postgres pg_dump -U ai_platform ai_platform > backup.sql

# Restore
docker-compose exec -T postgres psql -U ai_platform ai_platform < backup.sql
```

**Q: How to view API documentation?**

A: Visit http://localhost:8000/docs (AI Runtime FastAPI docs)

---

## 📄 License

MIT License

---

## 🤝 Contributing

Issues and Pull Requests are welcome!

---

## 📧 Contact

For questions, please submit an Issue.
