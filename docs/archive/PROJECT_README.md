# AI Platform

A production-ready AI platform with separate Go (platform layer) and Python (AI runtime) services, communicating via gRPC streaming.

## Architecture

```
┌──────────────────────────────┐
│           Client              │
│  Web / App / SDK / CLI        │
└────────────▲─────────────────┘
             │ SSE / WS
┌────────────┴─────────────────┐
│        Go Platform Layer      │  ← 平台"中枢"
│                               │
│  Auth / Tenant / Quota        │
│  SSE / WS / HTTP              │
│  RateLimit / Timeout          │
│  Cost / Token Metering        │
│  Guard / Audit / Log          │
│                               │
└────────────▲─────────────────┘
             │ gRPC Streaming
┌────────────┴─────────────────┐
│        Python AI Runtime      │  ← AI"大脑"
│                               │
│  Prompt Builder               │
│  RAG Pipeline                 │
│  LLM / LangChain              │
│  Agent / Tool                 │
│  Streaming Generator          │
│                               │
└────────────▲─────────────────┘
             │
┌────────────┴─────────────────┐
│   Infra Layer (Shared)        │
│  DB / Vector DB / Cache / MQ  │
└──────────────────────────────┘
```

## Project Structure

```
ai-platform/
├── proto/                    # gRPC protocol definitions
│   └── chat_service.proto
│
├── ai_runtime/              # Python AI Runtime
│   ├── api/                 # gRPC service implementation
│   ├── core/
│   │   ├── prompt/         # Prompt builder
│   │   ├── rag/            # RAG pipeline
│   │   ├── llm/            # LLM integrations (streaming)
│   │   ├── agent/          # Agent executor (streaming)
│   │   └── stream/         # Stream processing pipeline
│   ├── requirements.txt
│   └── main.py
│
└── platform/                # Go Platform Layer
    ├── api/
    │   ├── http/           # HTTP/SSE/WS handlers
    │   └── grpc/           # gRPC client
    ├── middleware/         # Auth, rate limit, guard, cost
    ├── service/            # Business logic
    ├── go.mod
    └── main.go
```

## Features

### Go Platform Layer
- **Authentication**: Bearer token auth
- **Rate Limiting**: Token bucket algorithm
- **Content Guard**: Safety checks and filtering
- **Cost Tracking**: Token usage metering
- **HTTP API**: RESTful endpoints
- **SSE**: Server-Sent Events streaming
- **WebSocket**: Real-time bidirectional communication

### Python AI Runtime
- **Prompt Builder**: Template-based prompt construction
- **RAG Pipeline**: Retrieval-augmented generation
- **LLM Integration**: OpenAI and local models
- **Agent System**: Tool-using agents with streaming
- **Stream Pipeline**: Middleware-based processing

## Quick Start

### 1. Setup Python AI Runtime

```bash
cd ai_runtime
pip install -r requirements.txt

# Generate gRPC stubs
python -m grpc_tools.protoc -I../proto --python_out=. --grpc_python_out=. ../proto/chat_service.proto

# Run
python main.py
```

### 2. Setup Go Platform Layer

```bash
cd platform
go mod download

# Generate gRPC stubs (optional)
protoc --go_out=. --go-grpc_out=. ../proto/chat_service.proto

# Run
go run main.go
```

## API Usage

### Health Check
```bash
curl http://localhost:8080/health
```

### Synchronous Chat
```bash
curl -X POST http://localhost:8080/api/v1/chat \
  -H "Authorization: Bearer your-token" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "session_123",
    "message": "Hello, how are you?",
    "config": {
      "model": "gpt-4",
      "temperature": 0.7,
      "use_rag": false,
      "use_agent": false
    }
  }'
```

### Streaming Chat (SSE)
```bash
curl -X POST http://localhost:8080/api/v1/chat/sse \
  -H "Authorization: Bearer your-token" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "session_123",
    "message": "Tell me a story"
  }'
```

### WebSocket Chat
```javascript
const ws = new WebSocket('ws://localhost:8080/api/v1/chat/ws');

ws.onopen = () => {
  ws.send(JSON.stringify({
    session_id: 'session_123',
    message: 'Hello via WebSocket!',
    config: {
      use_agent: true,
      tools: ['calculator', 'get_current_time']
    }
  }));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Received:', data);
};
```

## Configuration

### AI Runtime (Python)
Edit `ai_runtime/main.py`:
- Switch between LocalLLM and OpenAILLM
- Configure RAG settings
- Add custom tools
- Configure stream middlewares

### Platform Layer (Go)
Edit `platform/main.go`:
- AI Runtime address
- Platform port
- Rate limits (requests per minute)
- Cost quotas

## Development

### Generate Proto Stubs

For Python:
```bash
python -m grpc_tools.protoc -I./proto --python_out=./ai_runtime --grpc_python_out=./ai_runtime ./proto/chat_service.proto
```

For Go:
```bash
protoc --go_out=./platform --go-grpc_out=./platform ./proto/chat_service.proto
```

### Testing

Python:
```bash
cd ai_runtime
pytest
```

Go:
```bash
cd platform
go test ./...
```

## Production Deployment

1. **Containerize Services**
```bash
# Build Python runtime
docker build -t ai-runtime:latest ./ai_runtime

# Build Go platform
docker build -t platform:latest ./platform
```

2. **Deploy with Docker Compose**
```yaml
version: '3'
services:
  ai-runtime:
    image: ai-runtime:latest
    ports:
      - "50051:50051"

  platform:
    image: platform:latest
    ports:
      - "8080:8080"
    environment:
      - AI_RUNTIME_ADDR=ai-runtime:50051
```

3. **Use Kubernetes for scaling**
- Deploy with HPA for auto-scaling
- Use service mesh for observability
- Configure ingress for external access

## Monitoring

- **Metrics**: Prometheus metrics for both services
- **Logging**: Structured JSON logging
- **Tracing**: OpenTelemetry integration
- **Cost**: Real-time token usage tracking

## Security

- JWT-based authentication
- Rate limiting per user/tenant
- Content safety checks
- Input validation
- CORS configuration
- TLS/SSL in production

## License

MIT License
