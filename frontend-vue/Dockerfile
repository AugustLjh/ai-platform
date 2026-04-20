# Vue frontend build image.
ARG FRONTEND_NODE_IMAGE=node:20-alpine
FROM ${FRONTEND_NODE_IMAGE} AS builder

# 1. 配置 Alpine 镜像源 (清华)
RUN sed -i 's/dl-cdn.alpinelinux.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apk/repositories

WORKDIR /app

# 2. 配置 npm 镜像源（淘宝镜像）
RUN npm config set registry https://registry.npmmirror.com \
    && npm config set audit false \
    && npm config set fund false \
    && npm config set progress false

# 3. 复制依赖定义文件
COPY package*.json ./

# 4. 安装依赖（利用Docker缓存层）
RUN npm ci --only=production=false --no-audit --progress=false

# 5. 复制源代码
COPY . .

# 6. 构建生产版本
RUN npm run build
