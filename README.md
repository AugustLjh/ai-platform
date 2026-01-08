# AI Platform - Enterprise AI Application Platform

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Go Version](https://img.shields.io/badge/Go-1.21+-00ADD8?logo=go)](https://golang.org/)
[![Python Version](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python)](https://www.python.org/)

A production-ready AI application platform with microservices architecture using Go (Platform Layer) and Python (AI Runtime), communicating via gRPC streaming.

## 🌟 Key Features

### Platform Layer (Go)
- ✅ **JWT Authentication** - Complete user registration/login system
- ✅ **Multi-Tenancy** - Tenant isolation and management
- ✅ **Rate Limiting** - Token bucket algorithm
- ✅ **Content Security** - Request filtering and safety checks
- ✅ **Cost Tracking** - Token usage metering and cost calculation
- ✅ **Multi-Protocol** - HTTP/SSE/WebSocket support
- ✅ **Database Integration** - PostgreSQL + Redis + Elasticsearch

### AI Runtime (Python)
- ✅ **Prompt Builder** - Template-based prompt management
- ✅ **RAG Pipeline** - Retrieval-Augmented Generation
- ✅ **LLM Integration** - OpenAI and local model support
- ✅ **Agent System** - Tool-using agents
- ✅ **Streaming** - Complete streaming output support
- ✅ **Middleware Pipeline** - Extensible processing chain

### Databases
- ✅ **PostgreSQL** - Users, sessions, messages storage
- ✅ **Redis** - Cache, token blacklist, rate limiting
- ✅ **Elasticsearch** - Vector search, RAG support

### Frontend (Web UI)
- ✅ **Modern Interface** - Clean and responsive design
- ✅ **Real-time Chat** - Streaming responses with SSE
- ✅ **Session Management** - Multiple chat sessions
- ✅ **Mobile Friendly** - Works on all devices

## 📋 Table of Contents

- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Frontend UI](#frontend-ui)
- [Project Structure](#project-structure)
- [Features](#features)
- [API Documentation](#api-documentation)
- [Database Setup](#database-setup)
- [Development](#development)
- [Deployment](#deployment)
- [FAQ](#faq)

## 🏗️ Architecture

```
┌──────────────────────────────┐
│   Client (Web/App/CLI)        │
└────────────▲─────────────────┘
             │ SSE / WebSocket
┌────────────┴─────────────────┐
│    Go Platform Layer (Hub)    │
│                               │
│  ✓ JWT Authentication         │
│  ✓ Rate Limiting/Quotas       │
│  ✓ Cost Tracking              │
│  ✓ Content Security           │
│  ✓ Audit Logging              │
└────────────▲─────────────────┘
             │ gRPC Streaming
┌────────────┴─────────────────┐
│  Python AI Runtime (Brain)    │
│                               │
│  ✓ Prompt Builder             │
│  ✓ RAG Pipeline               │
│  ✓ LLM Integration            │
│  ✓ Agent Executor             │
│  ✓ Stream Processing          │
└────────────▲─────────────────┘
             │
┌────────────┴─────────────────┐
│    Database Infrastructure    │
│  PostgreSQL | Redis | ES      │
└──────────────────────────────┘
```

## 🚀 Quick Start

### Prerequisites

- **Docker & Docker Compose** (recommended)
- **Go 1.21+** (if running locally)
- **Python 3.11+** (if running locally)
- **PostgreSQL 16** (if not using Docker)
- **Redis 7** (if not using Docker)
- **Elasticsearch 8** (if not using Docker)

### Option 1: Docker Compose (Recommended)

```bash
# 1. Clone repository
git clone <repository-url>
cd ai-platform

# 2. Configure environment
cp .env.example .env
# Edit .env with your settings

# 3. Start all services
docker-compose --profile full up -d

# 4. View logs
docker-compose logs -f
```

Access:
- **API Service**: http://localhost:8080
- **Kibana** (optional): http://localhost:5601

### Option 2: Databases Only

```bash
# Start databases
./scripts/init-databases.sh  # Linux/Mac
# or
scripts\init-databases.bat   # Windows

# Start Python AI Runtime
cd ai_runtime
pip install -r requirements.txt
python main.py

# Start Go Platform (new terminal)
cd platform
go mod download
go run main.go
```

### Option 3: Development Scripts

```bash
# Linux/Mac
chmod +x start_dev.sh
./start_dev.sh

# Windows
start_dev.bat
```

## 🎨 Frontend UI

### Access the Web Interface

After starting the services, access the web interface:

**Option 1: Direct File Access**
```bash
cd frontend
open index.html  # Mac
start index.html # Windows
xdg-open index.html # Linux
```

**Option 2: Local Server**
```bash
cd frontend
python -m http.server 3000
# Visit http://localhost:3000
```

**Option 3: Via Platform** (add to platform/main.go)
```go
r.PathPrefix("/").Handler(http.FileServer(http.Dir("../frontend")))
```
Then visit: http://localhost:8080

### Demo Credentials

Use these credentials to test:
- **Email**: `demo@example.com`
- **Password**: `demo123456`

### Features

- **📱 Responsive Design**: Works on desktop, tablet, and mobile
- **💬 Real-time Chat**: Streaming AI responses
- **🎛️ Configurable**: Toggle RAG, Agent, adjust temperature
- **💾 Session History**: Multiple chat sessions with persistence
- **🎨 Modern UI**: Clean, intuitive interface

See [frontend/README.md](frontend/README.md) for more details.

## 📁 Project Structure

```
ai-platform/
├── platform/                    # Go Platform Layer
│   ├── api/
│   │   ├── http/               # HTTP/SSE/WebSocket handlers
│   │   │   ├── auth_handler.go
│   │   │   └── chat_handler.go
│   │   └── grpc/               # gRPC client
│   │       └── ai_client.go
│   ├── auth/                    # JWT authentication
│   │   ├── jwt.go
│   │   ├── user.go
│   │   └── service.go
│   ├── database/                # Database integration
│   │   ├── postgres.go
│   │   ├── redis.go
│   │   ├── elasticsearch.go
│   │   ├── user_store.go
│   │   └── session_store.go
│   ├── middleware/              # Middleware
│   │   ├── auth.go
│   │   ├── rate_limit.go
│   │   ├── guard.go
│   │   └── cost.go
│   ├── service/                 # Business logic
│   │   ├── chat_service.go
│   │   └── session_service.go
│   ├── main.go
│   └── go.mod
│
├── ai_runtime/                  # Python AI Runtime
│   ├── api/
│   │   └── chat_service.py
│   ├── core/
│   │   ├── prompt/             # Prompt management
│   │   ├── rag/                # RAG pipeline
│   │   ├── llm/                # LLM integration
│   │   ├── agent/              # Agent executor
│   │   └── stream/             # Stream processing
│   ├── main.py
│   └── requirements.txt
│
├── frontend/                    # Web UI
│   ├── index.html
│   ├── assets/
│   │   ├── css/
│   │   │   └── main.css        # Styles
│   │   └── js/
│   │       ├── config.js       # Configuration
│   │       ├── auth.js         # Authentication
│   │       ├── chat.js         # Chat logic
│   │       └── app.js          # Main app
│   └── README.md
│
├── db/
│   └── migrations/             # Database migrations
│       └── 001_initial_schema.sql
│
├── docs/                        # Documentation
│   ├── DATABASE_GUIDE.md
│   ├── JWT_AUTHENTICATION.md
│   └── JWT_IMPLEMENTATION_SUMMARY.md
│
├── examples/                    # Examples
│   ├── auth_examples.sh
│   ├── api_examples.sh
│   └── websocket_client_jwt.html
│
├── scripts/                     # Utility scripts
│   ├── init-databases.sh
│   └── generate_proto.sh
│
├── proto/                       # gRPC protocol definitions
│   └── chat_service.proto
│
├── docker-compose.yml
├── .env.example
└── README.md                    # This file
```

## ✨ Features

### 1. JWT Authentication System

Complete user authentication and authorization:

```bash
# Register user
curl -X POST http://localhost:8080/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"password123"}'

# Login
curl -X POST http://localhost:8080/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@example.com","password":"demo123456"}'
```

**Demo User:**
- Email: `demo@example.com`
- Password: `demo123456`

Details: [docs/JWT_AUTHENTICATION.md](docs/JWT_AUTHENTICATION.md)

### 2. Chat API

Three modes of chat interface:

#### Synchronous Chat
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

#### Streaming Chat (SSE)
```bash
curl -X POST http://localhost:8080/api/v1/chat/sse \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"session_id":"session_002","message":"Tell me a story"}'
```

#### WebSocket Chat
```javascript
const ws = new WebSocket('ws://localhost:8080/api/v1/chat/ws');
// See examples/websocket_client_jwt.html
```

### 3. Database Integration

#### PostgreSQL
- User management
- Session history
- Message storage
- Token usage tracking
- Audit logging

#### Redis
- API response caching
- JWT token blacklist
- Session data
- Distributed rate limiting

#### Elasticsearch
- Vector search (RAG)
- Document indexing
- Semantic search

Details: [docs/DATABASE_GUIDE.md](docs/DATABASE_GUIDE.md)

### 4. RAG (Retrieval-Augmented Generation)

```python
# Add documents to vector store
from core.rag import RAGPipeline, Document

documents = [
    Document(content="Document content...", metadata={"source": "doc1.pdf"}),
]
await rag_pipeline.add_documents(documents)

# Query with RAG
context = await rag_pipeline.process("User question", top_k=5)
```

### 5. Agent Tool System

```python
# Built-in tools
- get_current_time: Get current time
- calculator: Perform calculations

# Use agent
curl -X POST http://localhost:8080/api/v1/chat \
  -H "Authorization: Bearer <token>" \
  -d '{
    "message": "What time is it?",
    "config": {"use_agent": true, "tools": ["get_current_time"]}
  }'
```

## 📚 API Documentation

### Authentication Endpoints

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| POST | `/api/v1/auth/register` | User registration | No |
| POST | `/api/v1/auth/login` | User login | No |
| POST | `/api/v1/auth/refresh` | Refresh token | No |
| GET | `/api/v1/auth/me` | Get current user | Yes |
| POST | `/api/v1/auth/logout` | Logout | Yes |

### Chat Endpoints

| Method | Endpoint | Description | Auth Required |
|--------|----------|-------------|---------------|
| POST | `/api/v1/chat` | Synchronous chat | Yes |
| POST | `/api/v1/chat/sse` | Streaming chat (SSE) | Yes |
| WS | `/api/v1/chat/ws` | WebSocket chat | Yes |

### Health Check

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |

Full API documentation: [docs/JWT_AUTHENTICATION.md](docs/JWT_AUTHENTICATION.md)

## 💾 Database Setup

### Connection Information

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

### Initialize Databases

```bash
# Linux/Mac
./scripts/init-databases.sh

# Windows
scripts\init-databases.bat

# Or use Docker Compose
docker-compose up -d postgres redis elasticsearch
```

### Database Migrations

Migrations run automatically on PostgreSQL startup. To run manually:

```bash
psql -h localhost -U ai_platform -d ai_platform -f db/migrations/001_initial_schema.sql
```

Details: [docs/DATABASE_GUIDE.md](docs/DATABASE_GUIDE.md)

## 🔧 Development

### Environment Configuration

1. **Copy environment template**
```bash
cp .env.example .env
```

2. **Configure key variables**
```bash
# JWT secret (MUST change in production!)
JWT_SECRET=your-super-secret-key-change-in-production

# Database
POSTGRES_HOST=localhost
POSTGRES_PASSWORD=your-secure-password

# OpenAI (optional)
OPENAI_API_KEY=your-openai-api-key
```

### Generate gRPC Stubs

```bash
# Linux/Mac
chmod +x generate_proto.sh
./generate_proto.sh

# Windows
generate_proto.bat
```

### Local Development

**Start AI Runtime:**
```bash
cd ai_runtime
pip install -r requirements.txt
python main.py
```

**Start Platform:**
```bash
cd platform
go mod download
go run main.go
```

### Run Tests

**Go tests:**
```bash
cd platform
go test ./...
```

**Python tests:**
```bash
cd ai_runtime
pytest
```

### Code Style

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

## 🚢 Deployment

### Docker Deployment

```bash
# Build images
docker-compose build

# Start all services
docker-compose --profile full up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### Kubernetes Deployment

```bash
# Apply configuration
kubectl apply -f k8s/

# Check status
kubectl get pods
kubectl get services
```

### Production Checklist

- [ ] Change all default passwords
- [ ] Set strong JWT secret
- [ ] Enable HTTPS/TLS
- [ ] Configure firewall rules
- [ ] Set up database backups
- [ ] Configure log collection
- [ ] Set up monitoring & alerts
- [ ] Configure CDN (if needed)
- [ ] Enable rate limiting
- [ ] Configure error tracking

### Environment Variables (Production)

```bash
# Security
JWT_SECRET=<strong-random-string>
POSTGRES_PASSWORD=<strong-password>
REDIS_PASSWORD=<strong-password>

# Databases (use managed services)
POSTGRES_HOST=<RDS-address>
REDIS_HOST=<ElastiCache-address>
ELASTICSEARCH_URL=<OpenSearch-address>

# Feature flags
ENVIRONMENT=production
LOG_LEVEL=INFO
ENABLE_TELEMETRY=true
```

## ❓ FAQ

### Q: How to change JWT secret?

A: Set `JWT_SECRET` in `.env` file or as environment variable:
```bash
export JWT_SECRET="your-new-secret-key"
```

### Q: How to add new agent tools?

A: Create new tool class in `ai_runtime/core/agent/tools/`:
```python
class MyTool(Tool):
    def __init__(self):
        super().__init__("my_tool", "Tool description")

    async def execute(self, **kwargs):
        # Implement tool logic
        return result
```

### Q: How to switch to OpenAI?

A: Modify `ai_runtime/main.py`:
```python
from core.llm import OpenAILLM

# Replace LocalLLM
self.llm = OpenAILLM(
    model="gpt-4",
    api_key=os.getenv("OPENAI_API_KEY")
)
```

### Q: How to add RAG documents?

A: Use Elasticsearch API or code:
```python
from database import ElasticsearchVectorStore

# Index document
doc = VectorDocument(
    id="doc-1",
    tenant_id="tenant-1",
    title="Document Title",
    content="Document content",
    embedding=vector  # Get from embedding model
)
await vector_store.IndexDocument(ctx, doc)
```

### Q: Database connection failed?

A: Check:
1. Database services running: `docker-compose ps`
2. Connection info correct: check `.env`
3. Firewall rules
4. View logs: `docker-compose logs postgres`

### Q: How to backup data?

A:
```bash
# PostgreSQL backup
docker-compose exec postgres pg_dump -U ai_platform ai_platform > backup.sql

# Restore
docker-compose exec -T postgres psql -U ai_platform ai_platform < backup.sql

# Redis backup
docker-compose exec redis redis-cli SAVE
```

## 📖 Documentation Index

- **[Quick Start](QUICKSTART.md)** - 5-minute guide
- **[JWT Authentication](docs/JWT_AUTHENTICATION.md)** - Complete auth guide
- **[Database Guide](docs/DATABASE_GUIDE.md)** - Database setup and usage
- **[API Reference](docs/API_REFERENCE.md)** - Complete API docs
- **[Deployment Guide](docs/DEPLOYMENT.md)** - Production deployment
- **[Development Guide](docs/DEVELOPMENT.md)** - Developer docs

## 🤝 Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md)

## 📄 License

This project is licensed under the MIT License - see [LICENSE](LICENSE) file

## 🙏 Acknowledgments

- OpenAI - LLM support
- LangChain - AI framework
- PostgreSQL - Database
- Redis - Cache
- Elasticsearch - Search engine

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/your-org/ai-platform/issues)
- **Discussions**: [GitHub Discussions](https://github.com/your-org/ai-platform/discussions)
- **Documentation**: [docs/](docs/)

---

**Enjoy! Check docs or submit issues for any questions.** 🚀
