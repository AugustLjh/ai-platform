# Example API requests

## Health Check
curl http://localhost:8080/health

## Synchronous Chat
curl -X POST http://localhost:8080/api/v1/chat \
  -H "Authorization: Bearer demo-token-12345" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "session_001",
    "message": "What is the capital of France?",
    "config": {
      "model": "gpt-4",
      "temperature": 0.7,
      "max_tokens": 1000,
      "use_rag": false,
      "use_agent": false
    }
  }'

## Streaming Chat (SSE)
curl -X POST http://localhost:8080/api/v1/chat/sse \
  -H "Authorization: Bearer demo-token-12345" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "session_002",
    "message": "Tell me a short story about AI",
    "config": {
      "model": "gpt-4",
      "temperature": 0.9,
      "use_rag": false,
      "use_agent": false
    }
  }'

## Chat with Agent Tools
curl -X POST http://localhost:8080/api/v1/chat \
  -H "Authorization: Bearer demo-token-12345" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "session_003",
    "message": "What is the current time?",
    "config": {
      "use_agent": true,
      "tools": ["get_current_time", "calculator"]
    }
  }'

## Chat with RAG
curl -X POST http://localhost:8080/api/v1/chat \
  -H "Authorization: Bearer demo-token-12345" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "session_004",
    "message": "What do you know about our product documentation?",
    "config": {
      "use_rag": true,
      "use_agent": false
    }
  }'
