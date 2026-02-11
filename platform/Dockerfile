# ====== builder ======
FROM golang:1.21-alpine AS builder

# Alpine 镜像源（可保留）
RUN sed -i 's/dl-cdn.alpinelinux.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apk/repositories

WORKDIR /src/platform

# 编译依赖（protoc + git）
RUN apk add --no-cache git protobuf protobuf-dev

# Go proto 插件（建议固定版本，避免 @latest 漂移）
RUN go install google.golang.org/protobuf/cmd/protoc-gen-go@v1.33.0 && \
    go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@v1.3.0

# Go 模块代理（保留）
ENV GOPROXY=https://goproxy.cn,https://goproxy.io,direct
ENV GOSUMDB=sum.golang.google.cn

# 先拷依赖文件（缓存友好）
COPY platform/go.mod platform/go.sum ./

# 拷 proto 并准备 replace 目标（在 go mod download 之前）
COPY proto /proto
RUN mkdir -p proto/chat && \
    echo 'module github.com/ai-platform/platform/proto/chat' > proto/chat/go.mod && \
    echo '' >> proto/chat/go.mod && \
    echo 'go 1.21' >> proto/chat/go.mod && \
    echo '' >> proto/chat/go.mod && \
    echo 'require (' >> proto/chat/go.mod && \
    echo '	google.golang.org/grpc v1.60.0' >> proto/chat/go.mod && \
    echo '	google.golang.org/protobuf v1.31.0' >> proto/chat/go.mod && \
    echo ')' >> proto/chat/go.mod

RUN go mod download

# 拷 platform 源码
COPY platform/ ./

# 生成真实 proto（避免被 mock 覆盖）
RUN rm -rf proto/chat && \
    mkdir -p proto/chat && \
    protoc \
      -I/proto \
      --go_out=proto/chat --go_opt=paths=source_relative \
      --go-grpc_out=proto/chat --go-grpc_opt=paths=source_relative \
      /proto/chat_service.proto && \
    echo 'module github.com/ai-platform/platform/proto/chat' > proto/chat/go.mod && \
    echo '' >> proto/chat/go.mod && \
    echo 'go 1.21' >> proto/chat/go.mod && \
    echo '' >> proto/chat/go.mod && \
    echo 'require (' >> proto/chat/go.mod && \
    echo '	google.golang.org/grpc v1.60.0' >> proto/chat/go.mod && \
    echo '	google.golang.org/protobuf v1.31.0' >> proto/chat/go.mod && \
    echo ')' >> proto/chat/go.mod

# 构建二进制（静态）
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o /out/platform main.go

# ====== runtime ======
FROM alpine:3.19

RUN sed -i 's/dl-cdn.alpinelinux.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apk/repositories
RUN apk --no-cache add ca-certificates tzdata

RUN addgroup -g 1001 -S appuser && \
    adduser -u 1001 -S appuser -G appuser
USER appuser

WORKDIR /home/appuser

COPY --from=builder --chown=appuser:appuser /out/platform ./platform

EXPOSE 8080
ENV TZ=Asia/Shanghai

CMD ["./platform"]
