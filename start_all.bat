@echo off
REM AI Platform - Development Startup Script (Windows)
REM Starts all services with clear port information

echo.
echo ==================================================================
echo            AI Platform - Development Environment
echo ==================================================================
echo.

REM Check Python
echo Checking Prerequisites...
echo ------------------------------------------------------------------

python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python 3 is required but not installed.
    exit /b 1
)
echo [OK] Python found

REM Check Go
go version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [WARN] Go not found - Platform layer won't be available
    set GO_AVAILABLE=false
) else (
    echo [OK] Go found
    set GO_AVAILABLE=true
)

echo.
echo Installing Python Dependencies...
echo ------------------------------------------------------------------

cd ai_runtime

if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

echo Activating virtual environment...
call venv\Scripts\activate.bat

echo Installing requirements...
python -m pip install -q --upgrade pip
pip install -q -r requirements.txt

echo [OK] Python dependencies installed
cd ..

echo.
echo Starting Services...
echo ------------------------------------------------------------------
echo.

REM Start AI Runtime
echo Starting AI Runtime (Python)...
cd ai_runtime
call venv\Scripts\activate.bat
start "AI Runtime" cmd /k "python main.py --mode both"
cd ..
timeout /t 3 /nobreak >nul
echo [OK] AI Runtime started

REM Start Platform if Go is available
if "%GO_AVAILABLE%"=="true" (
    echo.
    echo Starting Platform Layer (Go)...
    cd platform
    start "Go Platform" cmd /k "go run main.go"
    cd ..
    timeout /t 2 /nobreak >nul
    echo [OK] Platform Layer started
)

echo.
echo ==================================================================
echo                All Services Started Successfully!
echo ==================================================================
echo.
echo Service Endpoints:
echo ------------------------------------------------------------------
echo.
echo AI Runtime (Python):
echo   HTTP API:      http://localhost:8000
echo   API Docs:      http://localhost:8000/docs
echo   Health Check:  http://localhost:8000/health
echo   gRPC:          localhost:50051
echo.

if "%GO_AVAILABLE%"=="true" (
    echo Platform Layer (Go):
    echo   HTTP API:      http://localhost:8080
    echo   Login:         http://localhost:8080/api/v1/auth/login
    echo   Chat (SSE^):    http://localhost:8080/api/v1/chat/sse
    echo   Health Check:  http://localhost:8080/health
    echo.
    echo Demo Account:
    echo   Email:    demo@example.com
    echo   Password: demo123456
    echo.
)

echo Frontend (Vue):
echo   Directory:     .\frontend-vue
echo   Start:         cd frontend-vue ^&^& npm run dev
echo.

echo ==================================================================
echo Quick Test Commands:
echo ------------------------------------------------------------------
echo.
echo # Test AI Runtime directly (no auth required^):
echo curl -X POST http://localhost:8000/api/v1/chat ^
echo   -H "Content-Type: application/json" ^
echo   -d "{\"session_id\": \"test\", \"message\": \"Hello!\", \"config\": {}}"
echo.

if "%GO_AVAILABLE%"=="true" (
    echo # Login to Platform:
    echo curl -X POST http://localhost:8080/api/v1/auth/login ^
    echo   -H "Content-Type: application/json" ^
    echo   -d "{\"email\": \"demo@example.com\", \"password\": \"demo123456\"}"
    echo.
)

echo ==================================================================
echo.
echo Close the terminal windows to stop services
echo.
pause