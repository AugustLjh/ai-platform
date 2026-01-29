# AI Runtime - Python Backend

This is the Python AI Runtime service that handles the core AI functionality.

## Features

- **Prompt Builder**: Template-based prompt construction
- **RAG Pipeline**: Retrieval-augmented generation with vector store
- **LLM Integration**: Support for OpenAI and local models with streaming
- **Agent Executor**: Tool-using agents with streaming support
- **Stream Pipeline**: Middleware-based stream processing

## Setup

Install dependencies:

```bash
pip install -r requirements.txt
```

Generate gRPC stubs:

```bash
python -m grpc_tools.protoc -I../proto --python_out=. --grpc_python_out=. ../proto/chat_service.proto
```

## Running

```bash
python main.py
```

## Architecture

```
ai_runtime/
├── api/                  # gRPC interface
├── core/
│   ├── prompt/          # Prompt building
│   ├── rag/             # RAG pipeline
│   ├── llm/             # LLM integrations (streaming)
│   ├── agent/           # Agent executor (streaming)
│   └── stream/          # Stream processing pipeline
└── main.py
```

## Configuration

Edit configuration in `main.py` to:
- Switch between LocalLLM and OpenAILLM
- Configure RAG settings
- Add custom tools to agent
- Configure stream middlewares
