# AI Platform - Project Overview

## 项目已完成生成！

根据 README.md 的架构设计，我已经成功生成了一个完整的 AI 平台项目，包含 Python AI Runtime 和 Go Platform Layer 两个主要服务。

## 📁 项目结构

```
ai-platform/
├── proto/                          # gRPC 协议定义
│   └── chat_service.proto
│
├── ai_runtime/                     # Python AI Runtime (AI 大脑)
│   ├── api/
│   │   ├── __init__.py
│   │   └── chat_service.py        # gRPC 服务实现
│   ├── core/
│   │   ├── __init__.py
│   │   ├── prompt/                # Prompt Builder (无生成器)
│   │   │   ├── __init__.py
│   │   │   ├── builder.py
│   │   │   └── templates/
│   │   │       └── default.json
│   │   ├── rag/                   # RAG Pipeline (无生成器)
│   │   │   ├── __init__.py
│   │   │   ├── retriever.py
│   │   │   └── pipeline.py
│   │   ├── llm/                   # LLM (支持流式)
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── openai.py
│   │   │   └── local.py
│   │   ├── agent/                 # Agent (支持流式)
│   │   │   ├── __init__.py
│   │   │   ├── executor.py
│   │   │   └── tools/
│   │   │       └── __init__.py
│   │   └── stream/                # 生成器管道
│   │       ├── __init__.py
│   │       ├── pipeline.py
│   │       └── middlewares.py
│   ├── __init__.py
│   ├── main.py                    # 主入口
│   ├── requirements.txt           # Python 依赖
│   ├── Dockerfile
│   └── README.md
│
├── platform/                       # Go Platform Layer (平台中枢)
│   ├── api/
│   │   ├── http/
│   │   │   └── chat_handler.go   # SSE / WebSocket / HTTP
│   │   └── grpc/
│   │       └── ai_client.go      # gRPC 客户端
│   ├── middleware/
│   │   ├── auth.go               # 认证
│   │   ├── rate_limit.go         # 限流
│   │   ├── guard.go              # 安全检查
│   │   └── cost.go               # 成本追踪
│   ├── service/
│   │   ├── chat_service.go       # 聊天服务
│   │   └── session_service.go    # 会话管理
│   ├── main.go                    # 主入口
│   ├── go.mod                     # Go 依赖
│   ├── Dockerfile
│   └── README.md
│
├── examples/                       # 示例代码
│   ├── api_examples.sh
│   └── websocket_client.html
│
├── docker-compose.yml
├── generate_proto.sh
├── generate_proto.bat
├── start_dev.sh
├── start_dev.bat
├── .gitignore
├── PROJECT_README.md              # 项目主文档
└── README.md                       # 原始需求文档
```

## ✨ 核心特性

### Python AI Runtime (AI 大脑)
- ✅ **Prompt Builder**: 模板化的 Prompt 构建器
- ✅ **RAG Pipeline**: 带向量存储的检索增强生成
- ✅ **LLM 集成**: 支持 OpenAI 和本地模型，完全流式输出
- ✅ **Agent 系统**: 工具使用型 Agent，支持流式响应
- ✅ **Stream Pipeline**: 中间件式的流处理管道
- ✅ **gRPC 服务**: 流式 gRPC 通信接口

### Go Platform Layer (平台中枢)
- ✅ **认证中间件**: Bearer Token 认证
- ✅ **限流中间件**: Token Bucket 算法
- ✅ **安全防护**: 内容过滤和安全检查
- ✅ **成本追踪**: Token 使用计量和成本计算
- ✅ **HTTP API**: RESTful 接口
- ✅ **SSE 流式**: Server-Sent Events 支持
- ✅ **WebSocket**: 双向实时通信
- ✅ **会话管理**: 自动会话清理

## 🚀 快速启动

### 方式 1: 使用启动脚本 (推荐)

**Windows:**
```bash
start_dev.bat
```

**Linux/Mac:**
```bash
chmod +x start_dev.sh
./start_dev.sh
```

### 方式 2: Docker Compose
```bash
docker-compose up
```

### 方式 3: 手动启动

**启动 Python AI Runtime:**
```bash
cd ai_runtime
pip install -r requirements.txt
python main.py
```

**启动 Go Platform:**
```bash
cd platform
go mod download
go run main.go
```

## 📡 API 使用示例

### 1. 健康检查
```bash
curl http://localhost:8080/health
```

### 2. 同步聊天
```bash
curl -X POST http://localhost:8080/api/v1/chat \
  -H "Authorization: Bearer demo-token-12345" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "session_001",
    "message": "Hello!",
    "config": {
      "model": "gpt-4",
      "temperature": 0.7,
      "use_rag": false,
      "use_agent": false
    }
  }'
```

### 3. 流式聊天 (SSE)
```bash
curl -X POST http://localhost:8080/api/v1/chat/sse \
  -H "Authorization: Bearer demo-token-12345" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "session_002",
    "message": "Tell me a story"
  }'
```

### 4. WebSocket 聊天
打开 `examples/websocket_client.html` 在浏览器中测试。

### 5. 使用 Agent 工具
```bash
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
```

## 🏗️ 架构说明

### 通信流程
```
Client (Web/App/CLI)
    ↓ HTTP/SSE/WS
Go Platform Layer (Port 8080)
    ↓ gRPC Streaming
Python AI Runtime (Port 50051)
    ↓
LLM / RAG / Agent
```

### 中间件链
```
Request → Auth → RateLimit → Guard → Cost → Handler → Response
```

### 流式处理
```
LLM/Agent → Stream Pipeline → Middleware → gRPC → Go Platform → SSE/WS → Client
```

## 📝 下一步开发建议

1. **生成 gRPC Stubs**
   ```bash
   # Windows 
   generate_proto.bat

   # Linux/Mac
   chmod +x generate_proto.sh
   ./generate_proto.sh
   ```

2. **配置 OpenAI API Key** (如果使用 OpenAI)
   ```python
   # 在 ai_runtime/main.py 中
   self.llm = OpenAILLM(model="gpt-4", api_key="your-key-here")
   ```

3. **添加数据库支持**
   - 用户认证: PostgreSQL / MySQL
   - 会话存储: Redis
   - 向量数据库: Pinecone / Weaviate / Milvus

4. **实现真实认证**
   - JWT token 验证
   - OAuth2 集成
   - API Key 管理

5. **添加监控**
   - Prometheus metrics
   - OpenTelemetry tracing
   - 结构化日志

6. **生产部署**
   - Kubernetes 配置
   - CI/CD pipeline
   - 负载均衡和自动扩展

## 🔧 配置说明

### Python AI Runtime 配置
编辑 `ai_runtime/main.py`:
- 切换 LLM (LocalLLM ↔ OpenAILLM)
- 配置 RAG 设置
- 添加自定义工具
- 配置流处理中间件

### Go Platform 配置
编辑 `platform/main.go`:
- AI Runtime 地址
- 平台端口
- 限流参数 (请求/分钟)
- 成本配额

## 📚 文档

- **项目主文档**: `PROJECT_README.md`
- **Python AI Runtime**: `ai_runtime/README.md`
- **Go Platform**: `platform/README.md`
- **API 示例**: `examples/api_examples.sh`

## 🎯 核心特点

1. **完全流式**: LLM 和 Agent 都支持流式输出
2. **模块化**: 清晰的层次结构，易于扩展
3. **生产就绪**: 包含认证、限流、成本追踪等企业级功能
4. **多协议支持**: HTTP、SSE、WebSocket
5. **Docker 支持**: 一键部署
6. **示例完整**: 包含多个使用示例

## 📦 依赖安装

### Python
```bash
cd ai_runtime
pip install -r requirements.txt
```

主要依赖:
- grpcio / grpcio-tools
- protobuf
- openai (可选)

### Go
```bash
cd platform
go mod download
```

主要依赖:
- google.golang.org/grpc
- github.com/gorilla/websocket

## ⚠️ 注意事项

1. **认证**: 当前使用的是 mock 认证，生产环境需要实现真实的 JWT 验证
2. **gRPC Stubs**: 需要运行 `generate_proto.sh/bat` 生成 gRPC 代码
3. **向量数据库**: 当前使用内存存储，生产环境建议使用 Pinecone/Weaviate
4. **OpenAI API**: 如需使用 OpenAI，需要配置 API Key

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License

---

**项目生成完成！开始探索你的 AI 平台吧！🎉**
