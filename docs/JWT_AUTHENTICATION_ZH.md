
## 演示用户

服务器启动时自动创建演示用户：

- **邮箱:** `demo@example.com`
- **密码:** `demo123456`

您可以使用此账户进行测试。

## 完整认证流程示例

```bash
# 1. 登录
LOGIN_RESPONSE=$(curl -s -X POST http://localhost:8080/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@example.com","password":"demo123456"}')

# 2. 提取访问令牌
ACCESS_TOKEN=$(echo $LOGIN_RESPONSE | jq -r '.access_token')

# 3. 使用令牌访问受保护端点
curl -X GET http://localhost:8080/api/v1/auth/me \
  -H "Authorization: Bearer $ACCESS_TOKEN"

# 4. 带认证的聊天
curl -X POST http://localhost:8080/api/v1/chat \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "session_001",
    "message": "你能做什么？"
  }'
```

## 错误响应

### 401 未授权

缺少或无效的令牌：

```json
{
  "error": "缺少 Authorization 请求头"
}
```

```json
{
  "error": "无效或过期的令牌"
}
```

### 400 错误请求

无效的请求数据：

```json
{
  "error": "密码必须至少8个字符"
}
```

### 409 冲突

用户已存在：

```json
{
  "error": "用户已存在"
}
```

## 令牌结构

### 访问令牌声明

```json
{
  "user_id": "user-uuid",
  "tenant_id": "tenant-uuid",
  "email": "user@example.com",
  "role": "user",
  "exp": 1704153600,
  "iat": 1704150000,
  "iss": "ai-platform",
  "sub": "user-uuid"
}
```

### 刷新令牌声明

```json
{
  "user_id": "user-uuid",
  "exp": 1704758400,
  "iat": 1704150000,
  "iss": "ai-platform",
  "sub": "user-uuid"
}
```

## 安全最佳实践

1. **更改 JWT 密钥**: 在生产环境中始终使用强且唯一的密钥
2. **使用 HTTPS**: 切勿通过未加密的连接发送令牌
3. **令牌存储**: 安全地存储令牌（httpOnly cookies 或安全存储）
4. **令牌过期**: 实现适当的令牌刷新流程
5. **密码策略**: 强制执行强密码（最少8个字符，复杂度规则）
6. **速率限制**: 已实现（每个用户每分钟100个请求）

## 生产环境考虑

### 数据库存储

将 `InMemoryUserStore` 替换为真实数据库：

```go
// PostgreSQL 示例
userStore := postgres.NewUserStore(db)
authService := auth.NewAuthService(userStore, tokenManager)
```

### 令牌黑名单

实现令牌撤销：

```go
// Redis 示例
tokenBlacklist := redis.NewTokenBlacklist(redisClient)
authMiddleware := middleware.NewAuthMiddleware(authService, tokenBlacklist)
```

### 密码重置

添加密码重置流程：

1. 请求重置 → 发送包含重置令牌的邮件
2. 验证重置令牌
3. 更新密码

### 邮箱验证

添加邮箱验证：

1. 注册时发送验证邮件
2. 验证邮箱后允许登录
3. 重新发送验证选项

## WebSocket 认证

对于 WebSocket 连接，您可以通过两种方式进行认证：

### 1. 查询参数（简单）

```javascript
const ws = new WebSocket('ws://localhost:8080/api/v1/chat/ws?token=' + accessToken);
```

### 2. 第一条消息（推荐）

```javascript
const ws = new WebSocket('ws://localhost:8080/api/v1/chat/ws');

ws.onopen = () => {
  // 首先发送认证消息
  ws.send(JSON.stringify({
    type: 'auth',
    token: accessToken
  }));

  // 然后发送正常消息
  ws.send(JSON.stringify({
    session_id: 'session_123',
    message: '你好！'
  }));
};
```

## 测试

### 手动测试

使用提供的演示凭据或注册新用户。

### 自动化测试

```bash
# 运行认证测试
go test ./auth/... -v

# 测试令牌生成
go test ./auth -run TestTokenManager

# 测试用户操作
go test ./auth -run TestUserStore
```

## 故障排除

### "无效或过期的令牌"

- 检查令牌是否过期（访问令牌1小时）
- 使用刷新令牌获取新的访问令牌
- 验证 JWT_SECRET 是否正确

### "缺少 Authorization 请求头"

- 确保发送了 `Authorization` 请求头
- 格式：`Authorization: Bearer <token>`

### "用户已存在"

- 使用不同的邮箱地址
- 或使用现有凭据登录

## 从模拟认证迁移

如果您正在从旧的模拟认证升级：

1. **更新请求**: 在访问受保护端点之前添加适当的登录流程
2. **存储令牌**: 保存登录响应中的访问和刷新令牌
3. **使用 Bearer 令牌**: 用真实的 JWT 令牌替换模拟令牌
4. **处理过期**: 在访问令牌过期时实现令牌刷新

## 总结

JWT 认证系统提供：

- ✅ 安全的基于令牌的认证
- ✅ 访问和刷新令牌流程
- ✅ 使用 bcrypt 的密码哈希
- ✅ 令牌过期和验证
- ✅ 用户角色和租户支持
- ✅ 用于测试的演示用户
- ✅ 生产就绪的架构

立即开始使用真实的 JWT 认证！🚀
