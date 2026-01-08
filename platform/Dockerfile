# Go Platform Layer Dockerfile
FROM golang:1.21-alpine AS builder

# Configure Alpine mirror (Tsinghua)
RUN sed -i 's/dl-cdn.alpinelinux.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apk/repositories

WORKDIR /app

# Install git (required for go mod download)
RUN apk add --no-cache git

# Copy go mod files
COPY go.mod go.sum ./

# Configure Go proxy with Chinese mirrors (Tsinghua, Aliyun, USTC)
#ENV GOPROXY=https://goproxy.cn,https://mirrors.aliyun.com/goproxy/,https://mirrors.ustc.edu.cn/goproxy/,https://goproxy.io,direct
#ENV GOSUMDB=off
#ENV GOPRIVATE=*

RUN go mod download

# Copy source code
COPY . .

# Build
RUN CGO_ENABLED=0 GOOS=linux go build -o platform main.go

# Final stage
FROM alpine:latest

# Configure Alpine mirror (Tsinghua)
RUN sed -i 's/dl-cdn.alpinelinux.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apk/repositories

RUN apk --no-cache add ca-certificates

WORKDIR /root/

# Copy binary from builder
COPY --from=builder /app/platform .

# Expose HTTP port
EXPOSE 8080

# Run
CMD ["./platform"]