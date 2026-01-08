#!/bin/bash

# Start AI Platform - Development Mode

echo "Starting AI Platform in Development Mode..."
echo ""

# Check dependencies
echo "Checking dependencies..."

# Python
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed"
    exit 1
fi

# Go
if ! command -v go &> /dev/null; then
    echo "Error: Go is not installed"
    exit 1
fi

echo "Dependencies OK"
echo ""

# Start AI Runtime (Python)
echo "Starting AI Runtime (Python)..."
cd ai_runtime
python3 main.py &
AI_RUNTIME_PID=$!
cd ..

echo "AI Runtime started (PID: $AI_RUNTIME_PID)"
sleep 2

# Start Platform (Go)
echo "Starting Platform Layer (Go)..."
cd platform
go run main.go &
PLATFORM_PID=$!
cd ..

echo "Platform started (PID: $PLATFORM_PID)"
echo ""
echo "="
echo "AI Platform is running!"
echo ""
echo "Services:"
echo "  - AI Runtime (gRPC): localhost:50051 (PID: $AI_RUNTIME_PID)"
echo "  - Platform (HTTP): http://localhost:8080 (PID: $PLATFORM_PID)"
echo ""
echo "Press Ctrl+C to stop all services"
echo "="

# Wait for interrupt
trap "kill $AI_RUNTIME_PID $PLATFORM_PID; exit" INT
wait
