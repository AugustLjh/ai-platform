@echo off
REM JWT Authentication Examples for AI Platform

set BASE_URL=http://localhost:8080

echo ==================================
echo AI Platform - JWT Auth Examples
echo ==================================
echo.

REM 1. Login with demo user
echo 1. Logging in with demo user...
curl -s -X POST "%BASE_URL%/api/v1/auth/login" ^
  -H "Content-Type: application/json" ^
  -d "{\"email\":\"demo@example.com\",\"password\":\"demo123456\"}" > login_response.json

type login_response.json
echo.
echo.

REM Extract access token (manual for Windows batch)
echo Please copy the access_token from above and paste it below:
set /p ACCESS_TOKEN="Access Token: "

REM 2. Get current user info
echo.
echo 2. Getting current user info...
curl -s -X GET "%BASE_URL%/api/v1/auth/me" ^
  -H "Authorization: Bearer %ACCESS_TOKEN%"
echo.
echo.

REM 3. Send chat message
echo 3. Sending chat message...
curl -s -X POST "%BASE_URL%/api/v1/chat" ^
  -H "Authorization: Bearer %ACCESS_TOKEN%" ^
  -H "Content-Type: application/json" ^
  -d "{\"session_id\":\"session_001\",\"message\":\"Hello!\"}"
echo.
echo.

REM 4. Test invalid token
echo 4. Testing with invalid token (should fail)...
curl -s -X GET "%BASE_URL%/api/v1/auth/me" ^
  -H "Authorization: Bearer invalid-token"
echo.
echo.

REM Cleanup
del login_response.json

echo ==================================
echo Examples completed!
echo ==================================
pause
