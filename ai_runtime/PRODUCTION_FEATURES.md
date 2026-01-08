# 生产级功能部署指南

本文档介绍如何部署和配置新增的生产级功能。

## 新增功能概览

✅ **已完成的生产级功能**:
1. 数据库连接池管理
2. 依赖注入系统
3. 审计日志
4. 配额限制
5. pgvector向量搜索优化
6. 环境配置管理

## 快速开始

### 1. 环境配置

复制环境变量示例文件：

```bash
cd ai_runtime
cp .env.example .env
```

编辑 `.env` 文件，配置数据库连接：

```env
# 数据库配置
DB_HOST=localhost
DB_PORT=5432
DB_USER=ai_user
DB_PASSWORD=your_secure_password
DB_NAME=ai_platform

# 其他默认配置通常不需要修改
```

### 2. 运行数据库迁移

```bash
# 基础schema（如果还未运行）
psql -U postgres -d ai_platform < ../db/migrations/001_initial_schema.sql

# 知识库增强
psql -U postgres -d ai_platform < ../db/migrations/002_knowledge_base_enhancements.sql

# （可选）pgvector优化 - 需要先安装pgvector扩展
# psql -U postgres -d ai_platform < ../db/migrations/003_enable_pgvector.sql
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 启动服务

```bash
python main.py
```

或指定端口：

```bash
python main.py --http-port 8080 --grpc-port 50052
```

## 详细配置说明

### 环境变量完整列表

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| **数据库** |||
| `DB_HOST` | localhost | 数据库主机 |
| `DB_PORT` | 5432 | 数据库端口 |
| `DB_USER` | ai_user | 数据库用户 |
| `DB_PASSWORD` | | 数据库密码 |
| `DB_NAME` | ai_platform | 数据库名 |
| `DB_MIN_POOL_SIZE` | 5 | 最小连接数 |
| `DB_MAX_POOL_SIZE` | 20 | 最大连接数 |
| **向量嵌入** |||
| `EMBEDDING_MODEL` | paraphrase-multilingual-MiniLM-L12-v2 | 模型名称 |
| `EMBEDDING_DEVICE` | cpu | 计算设备（cpu/cuda） |
| `EMBEDDING_CACHE_FOLDER` | | 模型缓存目录 |
| **配额限制** |||
| `MAX_DOCUMENTS_PER_TENANT` | 10000 | 每租户最大文档数 |
| `MAX_DOCUMENT_SIZE` | 10485760 | 最大文档大小（字节） |
| `MAX_UPLOAD_FILE_SIZE` | 20971520 | 最大上传文件大小 |
| **向量搜索** |||
| `USE_PGVECTOR` | false | 是否使用pgvector |
| **服务器** |||
| `SERVER_HOST` | 0.0.0.0 | 服务器监听地址 |
| `HTTP_PORT` | 8000 | HTTP端口 |
| `GRPC_PORT` | 50051 | gRPC端口 |
| **功能开关** |||
| `ENABLE_AUDIT_LOG` | true | 启用审计日志 |

### 生产环境建议配置

```env
# 生产环境 .env 示例

# 数据库（使用真实凭证）
DB_HOST=prod-db.example.com
DB_PORT=5432
DB_USER=ai_user
DB_PASSWORD=strong_password_here
DB_NAME=ai_platform
DB_MIN_POOL_SIZE=10
DB_MAX_POOL_SIZE=50

# 向量嵌入（GPU加速）
EMBEDDING_MODEL=paraphrase-multilingual-mpnet-base-v2
EMBEDDING_DEVICE=cuda
EMBEDDING_CACHE_FOLDER=/var/cache/models

# 配额（根据需求调整）
MAX_DOCUMENTS_PER_TENANT=100000
MAX_DOCUMENT_SIZE=52428800  # 50MB
MAX_UPLOAD_FILE_SIZE=104857600  # 100MB

# 启用pgvector
USE_PGVECTOR=true

# 服务器
SERVER_HOST=0.0.0.0
HTTP_PORT=8000
GRPC_PORT=50051

# 功能
ENABLE_AUDIT_LOG=true
ENVIRONMENT=production
LOG_LEVEL=WARNING
```

## 功能详解

### 1. 数据库连接池

**特性**:
- 自动管理连接池大小
- 健康检查
- 优雅关闭
- 事务支持

**监控连接池**:
```python
from core.database import get_db_manager

db_manager = get_db_manager()
pool = db_manager.pool

# 查看连接池状态
print(f"Free connections: {pool.get_size() - pool.get_idle_size()}")
print(f"Idle connections: {pool.get_idle_size()}")
```

### 2. 依赖注入

**架构**:
```
main.py
  └─> ServiceContainer
       ├─> EmbeddingService
       ├─> KnowledgeBaseRepository
       ├─> AuditLogger
       ├─> QuotaManager
       └─> KnowledgeBaseService
```

**访问服务**:
```python
from core.dependencies import get_container

container = get_container()
kb_service = container.kb_service
```

### 3. 审计日志

**记录的操作**:
- 文档创建/更新/删除
- 文档搜索
- 文件上传
- URL抓取
- 批量操作

**查询审计日志**:
```sql
-- 查看最近的操作
SELECT * FROM audit_logs
ORDER BY created_at DESC
LIMIT 100;

-- 查看特定用户的操作
SELECT action, resource_type, created_at
FROM audit_logs
WHERE user_id = 'user-id-here'
ORDER BY created_at DESC;

-- 统计操作类型
SELECT action, COUNT(*) as count
FROM audit_logs
WHERE created_at > NOW() - INTERVAL '24 hours'
GROUP BY action
ORDER BY count DESC;
```

### 4. 配额限制

**自动检查**:
- 创建文档前检查租户配额
- 检查文档大小
- 检查上传文件大小

**配额超限响应**:
```json
{
  "detail": "Document quota exceeded: 10001/10000. Please contact support to increase your limit.",
  "status_code": 429
}
```

**查看配额使用**:
```bash
curl http://localhost:8000/api/v1/knowledge/stats
```

**手动配额管理**:
```sql
-- 查看租户配额
SELECT * FROM quotas WHERE tenant_id = 'tenant-id';

-- 更新配额
UPDATE quotas
SET limit_value = 50000
WHERE tenant_id = 'tenant-id' AND quota_type = 'documents';
```

### 5. pgvector优化

**安装pgvector**:
```bash
# Ubuntu/Debian
sudo apt-get install postgresql-16-pgvector

# macOS
brew install pgvector

# 或从源码编译
git clone --branch v0.5.0 https://github.com/pgvector/pgvector.git
cd pgvector
make
make install  # 可能需要 sudo
```

**启用pgvector**:
```bash
# 1. 运行迁移
psql -U postgres -d ai_platform < db/migrations/003_enable_pgvector.sql

# 2. 配置环境变量
echo "USE_PGVECTOR=true" >> .env

# 3. 重启服务
```

**性能对比**:
| 方法 | 10k文档 | 100k文档 | 1M文档 |
|------|---------|----------|--------|
| 原生数组 | ~200ms | ~2s | ~20s |
| pgvector | ~20ms | ~100ms | ~500ms |

**优化建议**:
```sql
-- 根据数据量调整索引参数
-- 小数据集（<10k）
CREATE INDEX USING ivfflat ... WITH (lists = 100);

-- 中等数据集（10k-100k）
CREATE INDEX USING ivfflat ... WITH (lists = 500);

-- 大数据集（>100k）
CREATE INDEX USING ivfflat ... WITH (lists = 1000);
```

## 监控和维护

### 健康检查

```bash
# 基本健康检查
curl http://localhost:8000/health

# 数据库连接检查
curl http://localhost:8000/api/v1/knowledge/stats
```

### 日志查看

```bash
# 启动时查看初始化日志
python main.py 2>&1 | grep "✅"

# 查看审计日志
tail -f /var/log/ai-runtime/audit.log
```

### 性能监控

**查询性能统计**:
```sql
-- 慢查询
SELECT query, calls, total_time, mean_time
FROM pg_stat_statements
WHERE query LIKE '%documents%'
ORDER BY mean_time DESC
LIMIT 10;

-- 索引使用情况
SELECT
    schemaname,
    tablename,
    indexname,
    idx_scan
FROM pg_stat_user_indexes
WHERE tablename = 'documents';
```

## 故障排查

### 问题1: 数据库连接失败

**错误**:
```
❌ Failed to create database pool: could not connect to server
```

**解决**:
1. 检查`.env`配置
2. 确认PostgreSQL正在运行
3. 检查防火墙规则
4. 验证数据库凭证

```bash
# 测试连接
psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME
```

### 问题2: 嵌入模型下载慢

**症状**: 首次启动时卡在"Loading embedding model"

**解决**:
```bash
# 使用国内镜像
export HF_ENDPOINT=https://hf-mirror.com

# 预下载模型
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"
```

### 问题3: 配额检查失败

**错误**:
```
QuotaError: Document quota exceeded
```

**解决**:
```sql
-- 临时增加配额
UPDATE quotas
SET limit_value = 20000
WHERE tenant_id = 'your-tenant-id';

-- 或在.env中调整
MAX_DOCUMENTS_PER_TENANT=20000
```

### 问题4: pgvector索引慢

**症状**: 向量搜索很慢

**解决**:
```sql
-- 检查索引是否存在
\d+ documents

-- 重建索引（调整lists参数）
DROP INDEX idx_documents_embedding_vector_ivfflat;
CREATE INDEX idx_documents_embedding_vector_ivfflat
ON documents USING ivfflat (embedding_vector vector_cosine_ops)
WITH (lists = 500);  -- 根据数据量调整

-- 更新统计信息
ANALYZE documents;
```

## 安全建议

### 1. 数据库安全
- ✅ 使用强密码
- ✅ 限制数据库访问IP
- ✅ 启用SSL/TLS连接
- ✅ 定期备份

### 2. API安全
- ⚠️ 实现JWT认证（待完成）
- ✅ 启用审计日志
- ✅ 配额限制
- ⚠️ 添加速率限制（建议）

### 3. 数据隐私
- ✅ 租户数据隔离
- ✅ 用户级权限
- ✅ 审计跟踪
- ⚠️ 数据加密（建议）

## 下一步

### 推荐优化
1. **实现JWT认证** - 替换临时的header认证
2. **添加Redis缓存** - 缓存搜索结果
3. **实现消息队列** - 异步处理大文件
4. **添加Prometheus监控** - 实时性能指标
5. **实现蓝绿部署** - 零停机更新

### 扩展功能
- 文档版本控制
- 文档标签系统
- 全文搜索（Elasticsearch）
- 文档自动分类
- 智能推荐

## 参考资料

- [asyncpg文档](https://magicstack.github.io/asyncpg/)
- [FastAPI依赖注入](https://fastapi.tiangolo.com/tutorial/dependencies/)
- [pgvector文档](https://github.com/pgvector/pgvector)
- [sentence-transformers文档](https://www.sbert.net/)

## 技术支持

遇到问题？查看日志：
```bash
# 查看启动日志
python main.py 2>&1 | tee startup.log

# 查看完整文档
cat KNOWLEDGE_BASE_API.md
```

更多信息请访问：http://localhost:8000/docs
