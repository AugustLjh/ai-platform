@echo off
REM Start AI Platform - Development Mode

echo Starting AI Platform in Development Mode...
echo.

REM Start AI Runtime (Python)
echo Starting AI Runtime (Python)...
cd ai_runtime
start "AI Runtime" python main.py
cd ..

timeout /t 2 /nobreak > nul

REM Start Platform (Go)
echo Starting Platform Layer (Go)...
cd platform
start "Platform" go run main.go
cd ..

echo.
echo ===================================
echo AI Platform is running!
echo.
echo Services:
echo   - AI Runtime (gRPC): localhost:50051
echo   - Platform (HTTP): http://localhost:8080
echo.
echo Press any key to view logs or close windows to stop...
echo ===================================
echo.

pause
