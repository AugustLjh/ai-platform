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
    && rm -rf /var/lib/apt/lists/*

# ---------- Python 依赖 ----------
# 先拷贝 requirements，利用 Docker cache
COPY requirements.txt .

RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ---------- 应用代码 ----------
COPY . .

# ---------- 端口 ----------
EXPOSE 8000 50051

# ---------- 启动 ----------
CMD ["python", "main.py"]
