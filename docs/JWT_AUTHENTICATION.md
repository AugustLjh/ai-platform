# JWT Authentication Guide

## Overview

The AI Platform now uses **real JWT (JSON Web Token) authentication** instead of mock authentication. All protected endpoints require a valid JWT access token.

## Architecture

```
User Registration/Login
    ↓
JWT Token Generation
    ↓
Access Token (1 hour) + Refresh Token (7 days)
    ↓
Token Validation on Protected Endpoints
    ↓
Access Granted/Denied
```

## Features

- **JWT Access Tokens**: Short-lived (1 hour) tokens for API access
- **Refresh Tokens**: Long-lived (7 days) tokens to get new access tokens
- **Password Hashing**: bcrypt for secure password storage
- **Token Claims**: User ID, Tenant ID, Email, Role
- **In-Memory User Store**: For development (replace with database in production)

## Environment Variables

```bash
# JWT Secret (REQUIRED in production)
JWT_SECRET=your-secret-key-change-this-in-production

# Token TTL (optional)
ACCESS_TOKEN_TTL=1h
REFRESH_TOKEN_TTL=168h  # 7 days

# Server Configuration
PLATFORM_PORT=:8080
AI_RUNTIME_ADDR=localhost:50051
```

## API Endpoints

### 1. User Registration

Register a new user account.

**Endpoint:** `POST /api/v1/auth/register`

**Request:**
```json
{
  "email": "user@example.com",
  "password": "your-password-min-8-chars",
  "tenant_id": "optional-tenant-id",
  "role": "user"
}
```

**Response:** (201 Created)
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "user": {
    "id": "user-uuid",
    "email": "user@example.com",
    "tenant_id": "tenant-uuid",
    "role": "user",
    "created_at": "2024-01-01T00:00:00Z",
    "active": true
  }
}
```

**Example:**
```bash
curl -X POST http://localhost:8080/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "newuser@example.com",
    "password": "securepass123"
  }'
```

### 2. User Login

Authenticate with email and password.

**Endpoint:** `POST /api/v1/auth/login`

**Request:**
```json
{
  "email": "user@example.com",
  "password": "your-password"
}
```

**Response:** (200 OK)
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "user": { ... }
}
```

**Example:**
```bash
curl -X POST http://localhost:8080/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "demo@example.com",
    "password": "demo123456"
  }'
```

### 3. Refresh Token

Get a new access token using refresh token.

**Endpoint:** `POST /api/v1/auth/refresh`

**Request:**
```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIs..."
}
```

**Response:** (200 OK)
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "user": { ... }
}
```

**Example:**
```bash
curl -X POST http://localhost:8080/api/v1/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{
    "refresh_token": "your-refresh-token-here"
  }'
```

### 4. Get Current User

Get information about the authenticated user.

**Endpoint:** `GET /api/v1/auth/me`

**Headers:**
```
Authorization: Bearer <access_token>
```

**Response:** (200 OK)
```json
{
  "id": "user-uuid",
  "email": "user@example.com",
  "tenant_id": "tenant-uuid",
  "role": "user"
}
```

**Example:**
```bash
curl -X GET http://localhost:8080/api/v1/auth/me \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..."
```

### 5. Logout

Logout (client-side token deletion).

**Endpoint:** `POST /api/v1/auth/logout`

**Headers:**
```
Authorization: Bearer <access_token>
```

**Response:** (200 OK)
```json
{
  "message": "Logout successful. Please delete your tokens."
}
```

## Using JWT Tokens

### Protected Endpoints

All chat endpoints require authentication:

```bash
# Chat with authentication
curl -X POST http://localhost:8080/api/v1/chat \
  -H "Authorization: Bearer <your-access-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "session_123",
    "message": "Hello!"
  }'
```

### Token Format

Always use the `Bearer` authentication scheme:

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

## Demo User

A demo user is automatically created on server startup:

- **Email:** `demo@example.com`
- **Password:** `demo123456`

You can use this account for testing.

## Complete Authentication Flow Example

```bash
# 1. Login
LOGIN_RESPONSE=$(curl -s -X POST http://localhost:8080/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@example.com","password":"demo123456"}')

# 2. Extract access token
ACCESS_TOKEN=$(echo $LOGIN_RESPONSE | jq -r '.access_token')

# 3. Use token for protected endpoints
curl -X GET http://localhost:8080/api/v1/auth/me \
  -H "Authorization: Bearer $ACCESS_TOKEN"

# 4. Chat with authentication
curl -X POST http://localhost:8080/api/v1/chat \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "session_001",
    "message": "What can you do?"
  }'
```

## Error Responses

### 401 Unauthorized

Missing or invalid token:

```json
{
  "error": "Missing Authorization header"
}
```

```json
{
  "error": "Invalid or expired token"
}
```

### 400 Bad Request

Invalid request data:

```json
{
  "error": "password must be at least 8 characters"
}
```

### 409 Conflict

User already exists:

```json
{
  "error": "user already exists"
}
```

## Token Structure

### Access Token Claims

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

### Refresh Token Claims

```json
{
  "user_id": "user-uuid",
  "exp": 1704758400,
  "iat": 1704150000,
  "iss": "ai-platform",
  "sub": "user-uuid"
}
```

## Security Best Practices

1. **Change JWT Secret**: Always use a strong, unique secret in production
2. **Use HTTPS**: Never send tokens over unencrypted connections
3. **Token Storage**: Store tokens securely (httpOnly cookies or secure storage)
4. **Token Expiration**: Implement proper token refresh flow
5. **Password Policy**: Enforce strong passwords (min 8 chars, complexity rules)
6. **Rate Limiting**: Already implemented (100 requests/minute per user)

## Production Considerations

### Database Storage

Replace `InMemoryUserStore` with a real database:

```go
// Example with PostgreSQL
userStore := postgres.NewUserStore(db)
authService := auth.NewAuthService(userStore, tokenManager)
```

### Token Blacklist

Implement token revocation:

```go
// Example with Redis
tokenBlacklist := redis.NewTokenBlacklist(redisClient)
authMiddleware := middleware.NewAuthMiddleware(authService, tokenBlacklist)
```

### Password Reset

Add password reset flow:

1. Request reset → Send email with reset token
2. Verify reset token
3. Update password

### Email Verification

Add email verification:

1. Send verification email on registration
2. Verify email before allowing login
3. Resend verification option

## WebSocket Authentication

For WebSocket connections, you can authenticate in two ways:

### 1. Query Parameter (Simple)

```javascript
const ws = new WebSocket('ws://localhost:8080/api/v1/chat/ws?token=' + accessToken);
```

### 2. First Message (Recommended)

```javascript
const ws = new WebSocket('ws://localhost:8080/api/v1/chat/ws');

ws.onopen = () => {
  // Send auth message first
  ws.send(JSON.stringify({
    type: 'auth',
    token: accessToken
  }));

  // Then send normal messages
  ws.send(JSON.stringify({
    session_id: 'session_123',
    message: 'Hello!'
  }));
};
```

## Testing

### Manual Testing

Use the provided demo credentials or register a new user.

### Automated Testing

```bash
# Run auth tests
go test ./auth/... -v

# Test token generation
go test ./auth -run TestTokenManager

# Test user operations
go test ./auth -run TestUserStore
```

## Troubleshooting

### "Invalid or expired token"

- Check if token is expired (1 hour for access tokens)
- Use refresh token to get a new access token
- Verify JWT_SECRET is correct

### "Missing Authorization header"

- Ensure you're sending the `Authorization` header
- Format: `Authorization: Bearer <token>`

### "user already exists"

- Use a different email address
- Or login with existing credentials

## Migration from Mock Auth

If you're upgrading from the old mock authentication:

1. **Update requests**: Add proper login flow before accessing protected endpoints
2. **Store tokens**: Save access and refresh tokens from login response
3. **Use Bearer tokens**: Replace mock tokens with real JWT tokens
4. **Handle expiration**: Implement token refresh when access token expires

## Summary

The JWT authentication system provides:

- ✅ Secure token-based authentication
- ✅ Access and refresh token flow
- ✅ Password hashing with bcrypt
- ✅ Token expiration and validation
- ✅ User role and tenant support
- ✅ Demo user for testing
- ✅ Production-ready architecture

Start using real JWT authentication today! 🚀
