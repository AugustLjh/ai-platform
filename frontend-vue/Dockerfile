# Vue Frontend Dockerfile
FROM docker.1ms.run/library/node:20-alpine AS builder

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

# ====== 最终运行阶段 ======
# 7. 使用 Nginx 作为 Web 服务器
FROM docker.1ms.run/library/nginx:alpine

# 8. 配置 Alpine 镜像源 (清华)
RUN sed -i 's/dl-cdn.alpinelinux.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apk/repositories

# 9. 从构建阶段复制构建产物
COPY --from=builder /app/dist /usr/share/nginx/html

# 10. 复制 Nginx 配置
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 11. 暴露端口（声明性，实际运行时需-p映射）
EXPOSE 80

# 12. 启动 Nginx
CMD ["nginx", "-g", "daemon off;"]
