
## 快速开始

### 1. 使用 Docker Compose 启动数据库

**Linux/Mac:**
```bash
chmod +x scripts/init-databases.sh
./scripts/init-databases.sh
```

**Windows:**
```cmd
scripts\init-databases.bat
```

**或手动启动:**
```bash
# 启动所有数据库
docker-compose up -d postgres redis elasticsearch

# 检查状态
docker-compose ps
```

### 2. 配置环境

复制 `.env.example` 到 `.env` 并配置：

```bash
cp .env.example .env
```

编辑 `.env` 文件，配置您的数据库凭据。

### 3. 运行应用

应用将在启动时自动连接到数据库。

```bash
cd platform
go run main.go
```

## PostgreSQL

### 架构设计

#### 核心表

1. **users** - 用户账户
2. **tenants** - 组织/租户
3. **sessions** - 聊天会话
4. **messages** - 聊天消息
5. **token_usage** - 令牌使用跟踪
6. **api_keys** - 用于编程访问的 API 密钥
7. **documents** - 用于 RAG 的文档
8. **audit_logs** - 审计日志
9. **quotas** - 使用配额

### 连接配置

```go
import "github.com/ai-platform/platform/database"

config := &database.PostgresConfig{
    Host:     "localhost",
    Port:     5432,
    Database: "ai_platform",
    User:     "postgres",
    Password: "ai_platform_password",
    SSLMode:  "disable",
    MaxConns: 25,
    MinConns: 5,
}

pool, err := database.NewPostgresDB(config)
if err != nil {
    log.Fatal(err)
}
defer pool.Close()
```

### 用户存储使用

```go
import "github.com/ai-platform/platform/database"

// 创建用户存储
userStore := database.NewPostgresUserStore(pool)

// 创建用户
user := &auth.User{
    ID:           "user-123",
    Email:        "user@example.com",
    PasswordHash: "hashed_password",
    TenantID:     "tenant-456",
    Role:         "user",
    Active:       true,
}

err := userStore.Create(user)

// 通过邮箱获取用户
user, err := userStore.GetByEmail("user@example.com")

// 更新用户
user.Role = "admin"
err = userStore.Update(user)
```

### 会话存储使用

```go
import "github.com/ai-platform/platform/database"

// 创建会话存储
sessionStore := database.NewSessionStore(pool)

// 创建会话
session := &database.Session{
    ID:       "session-123",
    UserID:   "user-123",
    TenantID: "tenant-456",
    Title:    "新聊天",
}

err := sessionStore.CreateSession(session)

// 添加消息
message := &database.Message{
    ID:        "msg-123",
    SessionID: "session-123",
    Role:      "user",
    Content:   "你好！",
}

err = sessionStore.AddMessage(message)

// 获取消息
messages, err := sessionStore.GetSessionMessages("session-123", 50, 0)
```

### 迁移

迁移在启动时自动应用。位于 `db/migrations/` 目录。

手动运行迁移：

```bash
psql -U ai_platform -d ai_platform -f db/migrations/001_initial_schema.sql
```

### 备份和恢复

**备份:**
```bash
docker-compose exec postgres pg_dump -U ai_platform ai_platform > backup.sql
```

**恢复:**
```bash
docker-compose exec -T postgres psql -U ai_platform ai_platform < backup.sql
```

## Redis

### 功能

1. **缓存** - 通用缓存
2. **令牌黑名单** - JWT 令牌撤销
3. **会话存储** - 用户会话
4. **速率限制** - 请求速率限制

### 连接配置

```go
import "github.com/ai-platform/platform/database"

config := &database.RedisConfig{
    Host:     "localhost",
    Port:     6379,
    Password: "",
    DB:       0,
}

client, err := database.NewRedisClient(config)
if err != nil {
    log.Fatal(err)
}
defer client.Close()
```

### 缓存使用

```go
import "github.com/ai-platform/platform/database"

cache := database.NewRedisCache(client)

// 设置值
err := cache.Set(ctx, "key", "value", 5*time.Minute)

// 获取值
value, err := cache.Get(ctx, "key")

// 删除
err = cache.Delete(ctx, "key")
```

### 令牌黑名单使用

```go
import "github.com/ai-platform/platform/database"

blacklist := database.NewTokenBlacklist(client)

// 添加令牌到黑名单
err := blacklist.Add(ctx, "token-id", 24*time.Hour)

// 检查是否在黑名单中
isBlacklisted, err := blacklist.IsBlacklisted(ctx, "token-id")
```

### 会话缓存使用

```go
import "github.com/ai-platform/platform/database"

sessionCache := database.NewSessionCache(client, 24*time.Hour)

// 存储会话
err := sessionCache.Set(ctx, "session-id", sessionData)

// 获取会话
data, err := sessionCache.Get(ctx, "session-id")

// 延长 TTL
err = sessionCache.Extend(ctx, "session-id")
```

### 速率限制使用

```go
import "github.com/ai-platform/platform/database"

rateLimiter := database.NewRateLimitCache(client)

// 增加计数器
count, err := rateLimiter.Increment(ctx, "user:123", time.Minute)

// 检查限制
if count > 100 {
    // 超出速率限制
}
```

## Elasticsearch

### 功能

1. **向量搜索** - 使用嵌入的语义搜索
2. **全文搜索** - 传统文本搜索
3. **文档存储** - 存储用于 RAG 的文档

### 连接配置

```go
import "github.com/ai-platform/platform/database"

config := &database.ElasticsearchConfig{
    Addresses: []string{"http://localhost:9200"},
    Username:  "",
    Password:  "",
}

client, err := database.NewElasticsearchClient(config)
if err != nil {
    log.Fatal(err)
}
```

### 向量存储使用

```go
import "github.com/ai-platform/platform/database"

// 创建向量存储
vectorStore := database.NewElasticsearchVectorStore(client, "documents")

// 创建索引（为 OpenAI 嵌入设置 1536 维度）
err := vectorStore.CreateIndex(ctx, 1536)

// 索引带嵌入的文档
doc := &database.VectorDocument{
    ID:        "doc-123",
    TenantID:  "tenant-456",
    Title:     "示例文档",
    Content:   "这是一个示例文档...",
    Embedding: []float32{0.1, 0.2, 0.3, ...}, // 1536 维度
    Metadata:  map[string]interface{}{"source": "upload"},
    CreatedAt: time.Now(),
}

err = vectorStore.IndexDocument(ctx, doc)

// 通过向量搜索
queryVector := []float32{0.1, 0.2, 0.3, ...}
results, err := vectorStore.SearchByVector(ctx, queryVector, "tenant-456", 5)

// 通过文本搜索
results, err := vectorStore.SearchByText(ctx, "示例查询", "tenant-456", 5)
```

### Kibana（可选）

启动 Kibana 进行可视化：

```bash
docker-compose --profile observability up -d kibana
```

访问地址：http://localhost:5601

## Docker Compose 配置

### 仅启动数据库

```bash
docker-compose up -d postgres redis elasticsearch
```

### 启动完整平台

```bash
docker-compose --profile full up -d
```

### 停止服务

```bash
docker-compose down
```

### 删除卷（清理状态）

```bash
docker-compose down -v
```

### 查看日志

```bash
# 所有服务
docker-compose logs -f

# 特定服务
docker-compose logs -f postgres
```

## 连接字符串

### PostgreSQL

