# Go Platform Layer Dockerfile
FROM golang:1.21-alpine AS builder

# 1. 配置 Alpine 镜像源 (清华)
RUN sed -i 's/dl-cdn.alpinelinux.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apk/repositories

WORKDIR /app

# 2. 安装编译依赖 (git)
RUN apk add --no-cache git

# 3. 复制依赖定义文件
COPY go.mod ./

# 4. 【关键修复】配置 Go 模块代理和校验（国内镜像）
ENV GOPROXY=https://goproxy.cn,https://goproxy.io,direct
ENV GOSUMDB=sum.golang.google.cn

# 5. 生成 go.sum（如果不存在）并下载依赖（利用Docker缓存层）
RUN go mod tidy && go mod download

# 6. 复制源代码
COPY . .

# 7. 构建（剥离调试信息以减小体积）
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o platform main.go

# ====== 最终运行阶段 ======
# 8. 使用固定版本的 Alpine 镜像
FROM alpine:3.19

# 9. 配置 Alpine 镜像源 (清华)
RUN sed -i 's/dl-cdn.alpinelinux.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apk/repositories

# 10. 安装运行时依赖：CA证书、时区数据（可选）
RUN apk --no-cache add ca-certificates tzdata

# 11. 创建非root用户运行（安全增强）
RUN addgroup -g 1001 -S appuser && \
    adduser -u 1001 -S appuser -G appuser
USER appuser

WORKDIR /home/appuser/

# 12. 从构建阶段复制二进制文件
COPY --from=builder --chown=appuser:appuser /app/platform .

# 13. 暴露端口（声明性，实际运行时需-p映射）
EXPOSE 8080

# 14. 设置时区（可选，如 Asia/Shanghai）
ENV TZ=Asia/Shanghai

# 15. 启动应用
CMD ["./platform"]