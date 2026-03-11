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

# 生成到 /generated（不怕 /app volume 覆盖）
RUN mkdir -p /generated && \
    python -m grpc_tools.protoc \
      -I/proto \
      --python_out=/generated \
      --grpc_python_out=/generated \
      /proto/chat_service.proto && \
    touch /generated/__init__.py

# 让运行时能找到生成的模块
ENV PYTHONPATH=/generated

# ---------- 应用代码 ----------
COPY ai_runtime/ .

# ---------- 端口 ----------
EXPOSE 8000 50051

# ---------- 启动 ----------
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "-m", "main", "--mode", "both", "--http-port", "8000", "--grpc-port", "50051"]
