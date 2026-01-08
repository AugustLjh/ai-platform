# Python AI Runtime Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Configure pip to use Chinese mirrors (Tsinghua, Aliyun, USTC)
#RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple && \
#    pip config set global.extra-index-url "https://mirrors.aliyun.com/pypi/simple/ https://mirrors.ustc.edu.cn/pypi/web/simple/" && \
#    pip config set global.trusted-host "pypi.tuna.tsinghua.edu.cn mirrors.aliyun.com mirrors.ustc.edu.cn"


RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple && \
    pip config set global.extra-index-url "https://mirrors.aliyun.com/pypi/simple/ https://mirrors.ustc.edu.cn/pypi/web/simple/ https://pypi.org/simple" && \
    pip config set global.trusted-host "pypi.tuna.tsinghua.edu.cn mirrors.aliyun.com mirrors.ustc.edu.cn pypi.org"

# Install dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy source code
COPY . .

# Expose ports
EXPOSE 8000 50051

# Run the application
CMD ["python", "main.py"]
