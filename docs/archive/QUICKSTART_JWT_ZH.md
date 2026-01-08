
## 2. 测试认证

### 选项 A：使用示例脚本

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

### 选项 B：手动测试

**步骤 1：登录**
```bash
curl -X POST http://localhost:8080/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@example.com","password":"demo123456"}'
```

保存响应中的 `access_token`。

**步骤 2：使用受保护的端点**
```bash
curl -X POST http://localhost:8080/api/v1/chat \
  -H "Authorization: Bearer <your_access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test_session",
    "message": "Hello, AI!"
  }'
```

## 3. 尝试 WebSocket 客户端

在浏览器中打开 `examples/websocket_client_jwt.html`：

1. 输入凭据：
   - 邮箱：`demo@example.com`
   - 密码：`demo123456`

2. 点击"登录"

3. 点击"连接"建立 WebSocket 连接

4. 开始聊天！

## 4. 注册新用户

```bash
curl -X POST http://localhost:8080/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "newuser@example.com",
    "password": "securepass123"
  }'
```

## 常见问题

### "无效或过期的令牌"
- 令牌已过期（1 小时 TTL）
- 使用刷新令牌获取新的访问令牌

### "缺少 Authorization 头"
- 添加头：`Authorization: Bearer <token>`

### "用户已存在"
- 使用不同的邮箱或使用现有凭据登录

## 环境变量

```bash
# 可选 - 提供默认值
export JWT_SECRET="your-secret-key"
export PLATFORM_PORT=":8080"
export AI_RUNTIME_ADDR="localhost:50051"
```

## 下一步

- 阅读完整文档：`docs/JWT_AUTHENTICATION.md`
- 查看实现细节：`docs/JWT_IMPLEMENTATION_SUMMARY.md`
- 探索代码：`platform/auth/` 目录

---

**就是这样！您现在拥有生产就绪的 JWT 认证！🚀**
