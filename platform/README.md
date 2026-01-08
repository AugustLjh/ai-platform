# Platform Layer - Go Backend

This is the Go Platform Layer that handles authentication, rate limiting, cost tracking, and provides HTTP/SSE/WebSocket APIs.

## Features

- **Authentication**: Token-based auth middleware
- **Rate Limiting**: Token bucket rate limiter
- **Content Guard**: Safety checks and content filtering
- **Cost Tracking**: Token usage and cost metering
- **HTTP API**: RESTful endpoints
- **SSE**: Server-Sent Events for streaming
- **WebSocket**: Real-time bidirectional communication

## Setup

Initialize Go modules:

```bash
go mod download
```

Generate gRPC stubs (if proto files change):

```bash
protoc --go_out=. --go-grpc_out=. ../proto/chat_service.proto
```

## Running

```bash
go run main.go
```

The server will start on port 8080.

## API Endpoints

### Health Check
```
GET /health
```

### Synchronous Chat
```
POST /api/v1/chat
Authorization: Bearer <token>
Content-Type: application/json

{
  "session_id": "session_123",
  "message": "Hello!",
  "config": {
    "model": "gpt-4",
    "temperature": 0.7,
    "use_rag": false,
    "use_agent": false
  }
}
```

### Streaming Chat (SSE)
```
POST /api/v1/chat/sse
Authorization: Bearer <token>
Content-Type: application/json

{
  "session_id": "session_123",
  "message": "Hello!",
  "config": {...}
}
```

### WebSocket Chat
```
WS /api/v1/chat/ws
Authorization: Bearer <token>
```

## Architecture

```
platform/
├── api/
│   ├── http/         # HTTP/SSE/WS handlers
│   └── grpc/         # gRPC client for AI runtime
├── middleware/       # Auth, rate limit, guard, cost
├── service/          # Business logic
└── main.go
```

## Configuration

Edit `main.go` to configure:
- AI Runtime address
- Platform port
- Rate limits
- Cost quotas
