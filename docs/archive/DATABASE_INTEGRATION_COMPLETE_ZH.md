
## 🏭 生产环境考虑

### PostgreSQL
- 使用托管服务（AWS RDS、GCP Cloud SQL）
- 启用连接池
- 设置读取副本
- 配置备份
- 启用 SSL/TLS

### Redis
- 使用托管服务（AWS ElastiCache、Redis Labs）
- 启用持久化（AOF + RDB）
- 设置 Redis Sentinel/Cluster
- 配置最大内存策略
- 启用认证

### Elasticsearch
- 使用托管服务（AWS OpenSearch、Elastic Cloud）
- 配置适当的堆大小
- 设置快照
- 启用认证
- 使用 HTTPS

## 📈 监控

### 健康检查

**PostgreSQL:**
```bash
docker-compose exec postgres pg_isready -U ai_platform
```

**Redis:**
```bash
docker-compose exec redis redis-cli ping
```

**Elasticsearch:**
```bash
curl http://localhost:9200/_cluster/health
```

### 日志

```bash
# 所有数据库
docker-compose logs -f postgres redis elasticsearch

# 特定服务
docker-compose logs -f postgres
```

## 🔍 故障排除

### 常见问题

1. **连接被拒绝**：检查服务是否运行
2. **认证失败**：验证凭据
3. **内存不足**：调整 Docker 资源
4. **查询缓慢**：检查索引和查询计划

### 解决方案

**重启服务：**
```bash
docker-compose restart postgres redis elasticsearch
```

**清理状态：**
```bash
docker-compose down -v
docker-compose up -d
```

**查看日志：**
```bash
docker-compose logs --tail=100 postgres
```

## ✅ 集成检查清单

- [x] PostgreSQL 连接池
- [x] 用户存储实现
- [x] 会话存储实现
- [x] Redis 缓存实现
- [x] 令牌黑名单实现
- [x] Elasticsearch 向量存储
- [x] 数据库迁移
- [x] Docker Compose 配置
- [x] 健康检查
- [x] 初始化脚本
- [x] 环境配置
- [x] 完整文档
- [ ] 更新 main.go 以使用数据库（下一步）

## 📚 文档

- **完整指南**：`docs/DATABASE_GUIDE.md`
- **模式**：`db/migrations/001_initial_schema.sql`
- **示例**：查看 DATABASE_GUIDE.md 获取详细示例

## 🎊 总结

**数据库集成已完成！**

您现在拥有：
- ✅ **PostgreSQL** 用于可靠的数据存储
- ✅ **Redis** 用于缓存和实时功能
- ✅ **Elasticsearch** 用于强大的搜索能力
- ✅ **Docker Compose** 用于轻松部署
- ✅ **迁移脚本** 用于模式管理
- ✅ **完整文档** 用于所有功能

**下一步**：更新 `main.go` 以初始化和使用数据库。

---

**准备使用？从以下开始：**
```bash
./scripts/init-databases.sh
```

**有问题？** 查看 `docs/DATABASE_GUIDE.md` 获取详细信息！
