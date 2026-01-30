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
    && rm -rf /var/lib/apt/lists/*

# ---------- Python 依赖 ----------
# 先拷贝 requirements，利用 Docker cache
COPY requirements.txt .

RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ---------- Proto 文件生成 ----------
# 复制 proto 文件并生成 stubs
COPY ../proto /proto
RUN mkdir -p proto && \
    python -m grpc_tools.protoc \
    -I/proto \
    --python_out=./proto \
    --grpc_python_out=./proto \
    /proto/chat_service.proto && \
    touch proto/__init__.py

# ---------- 应用代码 ----------
COPY . .

# ---------- 端口 ----------
EXPOSE 8000 50051

# ---------- 启动 ----------
CMD ["python", "main.py"]
