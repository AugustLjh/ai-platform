
## 💡 使用示例

### 注册新用户

```bash
curl -X POST http://localhost:8080/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "newuser@example.com",
    "password": "securepass123"
  }'
```

### 登录

```bash
curl -X POST http://localhost:8080/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "demo@example.com",
    "password": "demo123456"
  }'
```

### 获取当前用户

```bash
curl -X GET http://localhost:8080/api/v1/auth/me \
  -H "Authorization: Bearer <token>"
```

### 刷新令牌

```bash
curl -X POST http://localhost:8080/api/v1/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"<refresh_token>"}'
```

### 带认证的聊天

```bash
curl -X POST http://localhost:8080/api/v1/chat \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "session_123",
    "message": "Hello!",
    "config": {"use_agent": true}
  }'
```

## 🔧 配置

### 环境变量

```bash
# 生产环境必需
JWT_SECRET=your-secret-key-change-this-in-production

# 可选
PLATFORM_PORT=:8080
AI_RUNTIME_ADDR=localhost:50051
```

### 令牌 TTL 配置

在 `main.go` 中：
```go
tokenManager := auth.NewTokenManager(
    jwtSecret,
    time.Hour,      // 访问令牌：1 小时
    24*time.Hour*7, // 刷新令牌：7 天
)
```

## 🏭 生产部署

### 1. 更改 JWT 密钥

```bash
# 生成强密钥
openssl rand -base64 32

# 设置为环境变量
export JWT_SECRET="your-generated-secret"
```

### 2. 替换内存存储

```go
// 在 main.go 中替换：
// userStore := auth.NewInMemoryUserStore()

// 使用数据库存储：
userStore := postgres.NewUserStore(db)
```

### 3. 添加 HTTPS

```go
// 在生产环境中使用 TLS
http.ListenAndServeTLS(":443", "cert.pem", "key.pem", mux)
```

### 4. 添加令牌黑名单（可选）

对于令牌撤销，使用 Redis：

```go
tokenBlacklist := redis.NewTokenBlacklist(redisClient)
// 在中间件中检查黑名单
```

## 🧪 测试

### 运行示例脚本

**Linux/Mac:**
```bash
cd examples
chmod +x auth_examples.sh
./auth_examples.sh
```

**Windows:**
```cmd
cd examples
auth_examples.bat
```

### WebSocket 客户端

在浏览器中打开 `examples/websocket_client_jwt.html`：

1. 使用演示凭据登录
2. 连接到 WebSocket
3. 开始与 AI 聊天

## 📈 从模拟认证迁移

**之前（模拟认证）：**
- 任何令牌都有效
- 无用户管理
- 无安全性

**之后（JWT 认证）：**
- 真实 JWT 验证
- 用户注册和登录
- 令牌过期
- 密码安全
- 生产就绪

## ✅ 检查清单

- [x] JWT 令牌生成和验证
- [x] 用户注册和登录
- [x] 密码哈希（bcrypt）
- [x] 令牌刷新流程
- [x] 受保护的端点
- [x] 中间件中的用户上下文
- [x] 演示用户创建
- [x] 环境变量配置
- [x] 完整的 API 文档
- [x] 使用示例
- [x] 带认证的 WebSocket 客户端
- [x] 错误处理
- [x] 生产环境考虑文档化

## 🎊 总结

**JWT 认证系统现已完成并生产就绪！**

主要改进：
- ✅ 真实 JWT 认证（不再模拟）
- ✅ 安全密码存储
- ✅ 令牌过期和刷新
- ✅ 用户管理系统
- ✅ 完整的 API 文档
- ✅ 工作示例
- ✅ 生产部署指南

**立即使用演示用户或注册新账户开始使用！**

---

**获取详细信息：**
- API 文档：`docs/JWT_AUTHENTICATION.md`
- 实现细节：`docs/JWT_IMPLEMENTATION_SUMMARY.md`
- 快速开始：`QUICKSTART_JWT.md`

**有问题？** 查看文档或检查 `platform/auth/` 中的代码
