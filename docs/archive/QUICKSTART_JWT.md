# Quick Start - JWT Authentication

## 1. Start the Server

```bash
cd platform
go mod download
go run main.go
```

You should see:

```
============================================================
AI Platform Server Configuration:
------------------------------------------------------------
  Platform Port: :8080
  AI Runtime: localhost:50051
  Auth: JWT (Real)
  Middleware: Auth, RateLimit, Guard, Cost

Auth Endpoints:
  - POST /api/v1/auth/register
  - POST /api/v1/auth/login
  - POST /api/v1/auth/refresh
  - GET  /api/v1/auth/me (protected)
  - POST /api/v1/auth/logout (protected)

Demo User:
  Email: demo@example.com
  Password: demo123456
============================================================
```

## 2. Test Authentication

### Option A: Use Example Script

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

### Option B: Manual Testing

**Step 1: Login**
```bash
curl -X POST http://localhost:8080/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@example.com","password":"demo123456"}'
```

Save the `access_token` from the response.

**Step 2: Use Protected Endpoint**
```bash
curl -X POST http://localhost:8080/api/v1/chat \
  -H "Authorization: Bearer <your_access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test_session",
    "message": "Hello, AI!"
  }'
```

## 3. Try WebSocket Client

Open `examples/websocket_client_jwt.html` in your browser:

1. Enter credentials:
   - Email: `demo@example.com`
   - Password: `demo123456`

2. Click "Login"

3. Click "Connect" to establish WebSocket connection

4. Start chatting!

## 4. Register New User

```bash
curl -X POST http://localhost:8080/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "newuser@example.com",
    "password": "securepass123"
  }'
```

## Common Issues

### "Invalid or expired token"
- Token expired (1 hour TTL)
- Use refresh token to get a new access token

### "Missing Authorization header"
- Add header: `Authorization: Bearer <token>`

### "user already exists"
- Use different email or login with existing credentials

## Environment Variables

```bash
# Optional - defaults provided
export JWT_SECRET="your-secret-key"
export PLATFORM_PORT=":8080"
export AI_RUNTIME_ADDR="localhost:50051"
```

## Next Steps

- Read full documentation: `docs/JWT_AUTHENTICATION.md`
- See implementation details: `docs/JWT_IMPLEMENTATION_SUMMARY.md`
- Explore code: `platform/auth/` directory

---

**That's it! You now have production-ready JWT authentication! 🚀**
