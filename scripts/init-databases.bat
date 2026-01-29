@echo off
REM Database initialization script for AI Platform

echo ======================================
echo AI Platform - Database Setup
echo ======================================
echo.

REM Check if docker-compose is installed
docker-compose --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: docker-compose is not installed
    exit /b 1
)

REM Start only database services
echo Starting database services...
docker-compose up -d postgres redis elasticsearch

echo.
echo Waiting for databases to be ready...
timeout /t 10 /nobreak >nul

REM Check services
echo Checking PostgreSQL...
docker-compose exec -T postgres pg_isready -U postgres
echo.

echo Checking Redis...
docker-compose exec -T redis redis-cli ping
echo.

echo Checking Elasticsearch...
curl -s http://localhost:9200/_cluster/health >nul
echo.

echo ======================================
echo Database Services Status:
echo ======================================
docker-compose ps postgres redis elasticsearch

echo.
echo ======================================
echo Connection Information:
echo ======================================
echo.
echo PostgreSQL:
echo   Host: localhost
echo   Port: 5432
echo   Database: ai_platform
echo   User: postgres
echo   Password: 19980912
echo.
echo Redis:
echo   Host: localhost
echo   Port: 6379
echo.
echo Elasticsearch:
echo   Host: localhost
echo   Port: 9200
echo   URL: http://localhost:9200
echo.
echo ======================================
echo Setup Complete!
echo ======================================

pause
