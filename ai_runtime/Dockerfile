FROM python:3.11-slim

# ---------- 基础环境 ----------
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# ---------- 系统依赖（按需） ----------
# 如果你有 grpc / cryptography / numpy / torch 等，通常需要这些
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    git \
    nodejs \
    npm \
    protobuf-compiler \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# ---------- Python 依赖 ----------
# 先拷贝 requirements，利用 Docker cache
COPY ai_runtime/requirements.txt requirements.txt

RUN pip install --upgrade pip \
    && pip install --no-cache-dir --no-compile -r requirements.txt

# ---------- Proto 文件生成 ----------
# 复制 proto 文件并生成 stubs
COPY proto /proto

# ---------- 应用代码 ----------
COPY ai_runtime /app/ai_runtime
COPY db /app/db

# 生成包内 proto stubs，避免运行时路径注入
RUN mkdir -p /app/ai_runtime/proto && \
    touch /app/ai_runtime/proto/__init__.py

RUN python -m grpc_tools.protoc \
      -I/proto \
      --python_out=/app/ai_runtime/proto \
      --grpc_python_out=/app/ai_runtime/proto \
      /proto/chat_service.proto && \
    sed -i 's/^import chat_service_pb2 as /from . import chat_service_pb2 as /' /app/ai_runtime/proto/chat_service_pb2_grpc.py

# ---------- 端口 ----------
EXPOSE 8000 50051

# ---------- 启动 ----------
RUN chmod +x /app/ai_runtime/entrypoint.sh

ENTRYPOINT ["/app/ai_runtime/entrypoint.sh"]
CMD ["python", "-m", "ai_runtime.main", "--mode", "both", "--http-port", "8000", "--grpc-port", "50051"]
