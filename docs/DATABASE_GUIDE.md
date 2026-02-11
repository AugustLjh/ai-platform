# Database Integration Guide

## Overview

The AI Platform uses three database systems:

1. **PostgreSQL** - Primary relational database for users, sessions, messages
2. **Redis** - Cache and session storage, token blacklist, rate limiting
3. **Elasticsearch** - Vector search for RAG (Retrieval-Augmented Generation)

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                     Go Platform Layer                     │
│                                                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │  PostgreSQL  │  │    Redis     │  │ Elasticsearch │   │
│  │    Store     │  │    Cache     │  │  Vector Store │   │
│  └──────────────┘  └──────────────┘  └──────────────┘   │
│          │                 │                  │            │
└──────────┼─────────────────┼──────────────────┼───────────┘
           │                 │                  │
       ┌───▼─────────────────▼──────────────────▼────┐
       │        Database Infrastructure Layer         │
       │                                               │
       │  ┌──────────┐  ┌────────┐  ┌──────────────┐ │
       │  │PostgreSQL│  │ Redis  │  │Elasticsearch │ │
       │  │   :5432  │  │ :6379  │  │    :9200     │ │
       │  └──────────┘  └────────┘  └──────────────┘ │
       └───────────────────────────────────────────────┘
```

## Quick Start

### 1. Start Databases with Docker Compose

**Linux/Mac:**
```bash
chmod +x scripts/init-databases.sh
./scripts/init-databases.sh
```

**Windows:**
```cmd
scripts\init-databases.bat
```

**Or manually:**
```bash
# Start all databases
docker-compose up -d postgres redis elasticsearch

# Check status
docker-compose ps
```

### 2. Configure Environment

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Edit `.env` with your database credentials.

### 3. Run Application

The application will automatically connect to databases on startup.

```bash
cd platform
go run main.go
```

## PostgreSQL

### Schema Design

#### Core Tables

1. **users** - User accounts
2. **tenants** - Organizations/tenants
3. **sessions** - Chat sessions
4. **messages** - Chat messages
5. **token_usage** - Token usage tracking
6. **api_keys** - API keys for programmatic access
7. **documents** - Documents for RAG
8. **audit_logs** - Audit trail
9. **quotas** - Usage quotas

### Connection Configuration

```go
import "github.com/ai-platform/platform/database"

config := &database.PostgresConfig{
    Host:     "localhost",
    Port:     5432,
    Database: "ai_platform",
    User:     "ai_platform",
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

### User Store Usage

```go
import "github.com/ai-platform/platform/database"

// Create user store
userStore := database.NewPostgresUserStore(pool)

// Create user
user := &auth.User{
    ID:           "user-123",
    Email:        "user@example.com",
    PasswordHash: "hashed_password",
    TenantID:     "tenant-456",
    Role:         "user",
    Active:       true,
}

err := userStore.Create(user)

// Get user by email
user, err := userStore.GetByEmail("user@example.com")

// Update user
user.Role = "admin"
err = userStore.Update(user)
```

### Session Store Usage

```go
import "github.com/ai-platform/platform/database"

// Create session store
sessionStore := database.NewSessionStore(pool)

// Create session
session := &database.Session{
    ID:       "session-123",
    UserID:   "user-123",
    TenantID: "tenant-456",
    Title:    "New Chat",
}

err := sessionStore.CreateSession(session)

// Add message
message := &database.Message{
    ID:        "msg-123",
    SessionID: "session-123",
    Role:      "user",
    Content:   "Hello!",
}

err = sessionStore.AddMessage(message)

// Get messages
messages, err := sessionStore.GetSessionMessages("session-123", 50, 0)
```

### Migrations

Migrations are automatically applied on startup. Located in `db/migrations/`.

To run migrations manually:

```bash
psql -U ai_platform -d ai_platform -f db/migrations/001_initial_schema.sql
psql -U ai_platform -d ai_platform -f db/migrations/002_knowledge_base_enhancements.sql
psql -U ai_platform -d ai_platform -f db/migrations/004_add_knowledge_bases.sql
psql -U ai_platform -d ai_platform -f db/migrations/005_migrate_existing_documents.sql
# Optional: pgvector optimization (requires pgvector extension)
# psql -U ai_platform -d ai_platform -f db/migrations/003_enable_pgvector.sql
```

### Backup and Restore

**Backup:**
```bash
docker-compose exec postgres pg_dump -U ai_platform ai_platform > backup.sql
```

**Restore:**
```bash
docker-compose exec -T postgres psql -U ai_platform ai_platform < backup.sql
```

## Redis

### Features

1. **Cache** - General purpose caching
2. **Token Blacklist** - JWT token revocation
3. **Session Storage** - User sessions
4. **Rate Limiting** - Request rate limiting

### Connection Configuration

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

### Cache Usage

```go
import "github.com/ai-platform/platform/database"

cache := database.NewRedisCache(client)

// Set value
err := cache.Set(ctx, "key", "value", 5*time.Minute)

// Get value
value, err := cache.Get(ctx, "key")

// Delete
err = cache.Delete(ctx, "key")
```

### Token Blacklist Usage

```go
import "github.com/ai-platform/platform/database"

blacklist := database.NewTokenBlacklist(client)

// Add token to blacklist
err := blacklist.Add(ctx, "token-id", 24*time.Hour)

// Check if blacklisted
isBlacklisted, err := blacklist.IsBlacklisted(ctx, "token-id")
```

### Session Cache Usage

```go
import "github.com/ai-platform/platform/database"

sessionCache := database.NewSessionCache(client, 24*time.Hour)

// Store session
err := sessionCache.Set(ctx, "session-id", sessionData)

// Get session
data, err := sessionCache.Get(ctx, "session-id")

// Extend TTL
err = sessionCache.Extend(ctx, "session-id")
```

### Rate Limiting Usage

```go
import "github.com/ai-platform/platform/database"

rateLimiter := database.NewRateLimitCache(client)

// Increment counter
count, err := rateLimiter.Increment(ctx, "user:123", time.Minute)

// Check limit
if count > 100 {
    // Rate limit exceeded
}
```

## Elasticsearch

### Features

1. **Vector Search** - Semantic search using embeddings
2. **Full-Text Search** - Traditional text search
3. **Document Storage** - Store documents for RAG

### Connection Configuration

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

### Vector Store Usage

```go
import "github.com/ai-platform/platform/database"

// Create vector store
vectorStore := database.NewElasticsearchVectorStore(client, "documents")

// Create index (with 1536 dimensions for OpenAI embeddings)
err := vectorStore.CreateIndex(ctx, 1536)

// Index document with embedding
doc := &database.VectorDocument{
    ID:        "doc-123",
    TenantID:  "tenant-456",
    Title:     "Sample Document",
    Content:   "This is a sample document...",
    Embedding: []float32{0.1, 0.2, 0.3, ...}, // 1536 dimensions
    Metadata:  map[string]interface{}{"source": "upload"},
    CreatedAt: time.Now(),
}

err = vectorStore.IndexDocument(ctx, doc)

// Search by vector
queryVector := []float32{0.1, 0.2, 0.3, ...}
results, err := vectorStore.SearchByVector(ctx, queryVector, "tenant-456", 5)

// Search by text
results, err := vectorStore.SearchByText(ctx, "sample query", "tenant-456", 5)
```

### Kibana (Optional)

Start Kibana for visualization:

```bash
docker-compose --profile observability up -d kibana
```

Access at: http://localhost:5601

## Docker Compose Configuration

### Start Only Databases

```bash
docker-compose up -d postgres redis elasticsearch
```

### Start Full Platform

```bash
docker-compose --profile full up -d
```

### Stop Services

```bash
docker-compose down
```

### Remove Volumes (Clean State)

```bash
docker-compose down -v
```

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f postgres
```

## Connection Strings

### PostgreSQL

```
postgresql://ai_platform:ai_platform_password@localhost:5432/ai_platform?sslmode=disable
```

### Redis

```
redis://localhost:6379/0
```

### Elasticsearch

```
http://localhost:9200
```

## Environment Variables

Set these in `.env` file or environment:

```bash
# PostgreSQL
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=ai_platform
POSTGRES_USER=ai_platform
POSTGRES_PASSWORD=ai_platform_password
POSTGRES_SSLMODE=disable
POSTGRES_MAX_CONNS=25
POSTGRES_MIN_CONNS=5

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0

# Elasticsearch
ELASTICSEARCH_URL=http://localhost:9200
ELASTICSEARCH_USERNAME=
ELASTICSEARCH_PASSWORD=
```

## Health Checks

### PostgreSQL

```bash
docker-compose exec postgres pg_isready -U ai_platform
```

Or with psql:
```bash
psql -h localhost -U ai_platform -d ai_platform -c "SELECT 1"
```

### Redis

```bash
docker-compose exec redis redis-cli ping
```

Or with redis-cli:
```bash
redis-cli -h localhost -p 6379 ping
```

### Elasticsearch

```bash
curl http://localhost:9200/_cluster/health
```

## Performance Tuning

### PostgreSQL

**Connection Pooling:**
```go
config.MaxConns = 25  // Maximum connections
config.MinConns = 5   // Minimum idle connections
```

**Query Optimization:**
- Use indexes on frequently queried columns
- Limit result sets
- Use prepared statements

### Redis

**Memory Management:**
```bash
# Set max memory
redis-cli CONFIG SET maxmemory 256mb
redis-cli CONFIG SET maxmemory-policy allkeys-lru
```

### Elasticsearch

**JVM Heap:**
```yaml
environment:
  - "ES_JAVA_OPTS=-Xms1g -Xmx1g"
```

## Monitoring

### PostgreSQL Stats

```sql
-- Active connections
SELECT count(*) FROM pg_stat_activity;

-- Slow queries
SELECT * FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;
```

### Redis Info

```bash
redis-cli INFO stats
redis-cli INFO memory
```

### Elasticsearch Stats

```bash
curl http://localhost:9200/_stats
curl http://localhost:9200/_cluster/stats
```

## Troubleshooting

### PostgreSQL Connection Issues

```bash
# Check if running
docker-compose ps postgres

# View logs
docker-compose logs postgres

# Restart
docker-compose restart postgres
```

### Redis Connection Issues

```bash
# Test connection
redis-cli -h localhost -p 6379 ping

# View logs
docker-compose logs redis
```

### Elasticsearch Issues

```bash
# Check cluster health
curl http://localhost:9200/_cluster/health

# View logs
docker-compose logs elasticsearch

# Increase memory
docker-compose down
# Edit docker-compose.yml: ES_JAVA_OPTS=-Xms1g -Xmx1g
docker-compose up -d elasticsearch
```

## Production Deployment

### Security

1. **Change default passwords**
2. **Enable SSL/TLS**
3. **Use connection encryption**
4. **Set up firewalls**
5. **Enable authentication**

### PostgreSQL Production

```bash
# Use managed PostgreSQL (AWS RDS, GCP Cloud SQL)
# Or set up replication for high availability

# Enable SSL
POSTGRES_SSLMODE=require
```

### Redis Production

```bash
# Use managed Redis (AWS ElastiCache, Redis Labs)
# Or set up Redis Sentinel/Cluster

# Enable authentication
REDIS_PASSWORD=strong-password
```

### Elasticsearch Production

```bash
# Use managed Elasticsearch (AWS OpenSearch, Elastic Cloud)
# Enable security features

# Authentication
ELASTICSEARCH_USERNAME=admin
ELASTICSEARCH_PASSWORD=strong-password

# HTTPS
ELASTICSEARCH_URL=https://elasticsearch:9200
```

### Backup Strategy

1. **PostgreSQL**: Daily automated backups
2. **Redis**: RDB snapshots + AOF
3. **Elasticsearch**: Snapshot API

## Summary

- ✅ **PostgreSQL**: User storage, sessions, messages, audit logs
- ✅ **Redis**: Cache, token blacklist, rate limiting, sessions
- ✅ **Elasticsearch**: Vector search for RAG, document storage
- ✅ **Docker Compose**: One-command setup
- ✅ **Connection Pooling**: Optimized performance
- ✅ **Health Checks**: Automatic service monitoring
- ✅ **Migration Scripts**: Automatic schema management

**Next Steps:**
1. Run `scripts/init-databases.sh` to start databases
2. Configure `.env` with your settings
3. Run the platform: `go run main.go`
4. Start building! 🚀

For more information:
- PostgreSQL: https://www.postgresql.org/docs/
- Redis: https://redis.io/documentation
- Elasticsearch: https://www.elastic.co/guide/
