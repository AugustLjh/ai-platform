#!/bin/bash

# JWT Authentication Examples for AI Platform

BASE_URL="http://localhost:8080"

echo "=================================="
echo "AI Platform - JWT Auth Examples"
echo "=================================="
echo ""

# 1. Register a new user
echo "1. Registering new user..."
REGISTER_RESPONSE=$(curl -s -X POST "$BASE_URL/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "testuser@example.com",
    "password": "testpass123"
  }')

echo "$REGISTER_RESPONSE" | jq '.'
echo ""

# 2. Login with demo user
echo "2. Logging in with demo user..."
LOGIN_RESPONSE=$(curl -s -X POST "$BASE_URL/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "demo@example.com",
    "password": "demo123456"
  }')

echo "$LOGIN_RESPONSE" | jq '.'
echo ""

# Extract tokens
ACCESS_TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r '.access_token')
REFRESH_TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r '.refresh_token')

if [ "$ACCESS_TOKEN" == "null" ] || [ -z "$ACCESS_TOKEN" ]; then
  echo "Failed to get access token. Exiting."
  exit 1
fi

echo "Access Token: $ACCESS_TOKEN"
echo ""

# 3. Get current user info
echo "3. Getting current user info..."
curl -s -X GET "$BASE_URL/api/v1/auth/me" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq '.'
echo ""

# 4. Use token for chat
echo "4. Sending chat message..."
curl -s -X POST "$BASE_URL/api/v1/chat" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "session_001",
    "message": "Hello, this is a test message with JWT auth!",
    "config": {
      "use_rag": false
    }
  }' | jq '.'
echo ""

# 5. Refresh token
echo "5. Refreshing access token..."
REFRESH_RESPONSE=$(curl -s -X POST "$BASE_URL/api/v1/auth/refresh" \
  -H "Content-Type: application/json" \
  -d "{
    \"refresh_token\": \"$REFRESH_TOKEN\"
  }")

echo "$REFRESH_RESPONSE" | jq '.'
echo ""

# 6. Test with invalid token
echo "6. Testing with invalid token (should fail)..."
curl -s -X GET "$BASE_URL/api/v1/auth/me" \
  -H "Authorization: Bearer invalid-token-12345" | jq '.'
echo ""

# 7. Logout
echo "7. Logging out..."
curl -s -X POST "$BASE_URL/api/v1/auth/logout" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq '.'
echo ""

echo "=================================="
echo "Examples completed!"
echo "=================================="
