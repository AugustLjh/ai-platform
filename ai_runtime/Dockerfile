# Python AI Runtime Dockerfile
FROM python:3.11-slim

WORKDIR /app
ENV ENV_FILE=/app/ai_runtime/.env

# Configure Hugging Face mirror for China (解决模型下载问题)
ENV HF_ENDPOINT=https://hf-mirror.com

# Configure pip to use Chinese mirrors
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/ && \
    pip config set global.timeout 3600 && \
    pip config set global.default-timeout 7200 && \
    pip config set install.retries 20 && \
    pip config set install.no-cache-dir false

# Install dependencies
COPY requirements.txt .
RUN pip install asyncpg && \
    pip install -r requirements.txt

# Copy source code
COPY . .

# Expose ports
EXPOSE 8000 50051

# Run the application
CMD ["python", "main.py"]
