#!/bin/bash
# AI Platform - Development Startup Script
# Starts all services with clear port information

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

print_banner() {
    echo ""
    echo "=================================================================="
    echo "           🚀 AI Platform - Development Environment"
    echo "=================================================================="
    echo ""
}

print_section() {
    echo ""
    echo -e "${CYAN}▶ $1${NC}"
    echo "──────────────────────────────────────────────────────────────────"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${BLUE}  $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_banner

# Check prerequisites
print_section "Checking Prerequisites"

command -v python3 >/dev/null 2>&1 || { print_error "Python 3 is required but not installed."; exit 1; }
print_success "Python 3 found: $(python3 --version)"

command -v go >/dev/null 2>&1 || { print_warning "Go not found - Platform layer won't be available"; GO_AVAILABLE=false; }
if [ "$GO_AVAILABLE" != "false" ]; then
    print_success "Go found: $(go version | cut -d' ' -f3)"
fi

# Install Python dependencies
print_section "Installing Python Dependencies"
cd ai_runtime
if [ ! -d "venv" ]; then
    print_info "Creating virtual environment..."
    python3 -m venv venv
fi

print_info "Activating virtual environment..."
source venv/bin/activate

print_info "Installing requirements..."
pip install -q --upgrade pip
pip install -q -r requirements.txt
print_success "Python dependencies installed"
cd ..

# Start services
print_section "Starting Services"

echo ""
print_info "Starting AI Runtime (Python)..."
cd ai_runtime
source venv/bin/activate
python main.py --mode both &
AI_RUNTIME_PID=$!
cd ..
sleep 3
print_success "AI Runtime started (PID: $AI_RUNTIME_PID)"

if [ "$GO_AVAILABLE" != "false" ]; then
    echo ""
    print_info "Starting Platform Layer (Go)..."
    cd platform
    go run main.go &
    PLATFORM_PID=$!
    cd ..
    sleep 2
    print_success "Platform Layer started (PID: $PLATFORM_PID)"
fi

# Print service information
echo ""
echo "=================================================================="
echo -e "${GREEN}✓ All Services Started Successfully!${NC}"
echo "=================================================================="
echo ""
echo -e "${CYAN}📡 Service Endpoints:${NC}"
echo "──────────────────────────────────────────────────────────────────"
echo ""
echo -e "${YELLOW}AI Runtime (Python):${NC}"
echo -e "  🌐 HTTP API:      ${GREEN}http://localhost:8000${NC}"
echo -e "  📚 API Docs:      ${GREEN}http://localhost:8000/docs${NC}"
echo -e "  ❤️  Health Check: ${GREEN}http://localhost:8000/health${NC}"
echo -e "  🔌 gRPC:          ${GREEN}localhost:50051${NC}"
echo ""

if [ "$GO_AVAILABLE" != "false" ]; then
    echo -e "${YELLOW}Platform Layer (Go):${NC}"
    echo -e "  🌐 HTTP API:      ${GREEN}http://localhost:8080${NC}"
    echo -e "  🔐 Login:         ${GREEN}http://localhost:8080/api/v1/auth/login${NC}"
    echo -e "  💬 Chat (SSE):    ${GREEN}http://localhost:8080/api/v1/chat/sse${NC}"
    echo -e "  ❤️  Health Check: ${GREEN}http://localhost:8080/health${NC}"
    echo ""
    echo -e "${YELLOW}Demo Account:${NC}"
    echo -e "  Email:    ${CYAN}demo@example.com${NC}"
    echo -e "  Password: ${CYAN}demo123456${NC}"
    echo ""
fi

echo -e "${YELLOW}Frontend (Vue):${NC}"
echo -e "  📂 Directory:     ${CYAN}./frontend-vue${NC}"
echo -e "  🚀 Start:         ${CYAN}cd frontend-vue && npm run dev${NC}"
echo ""

echo "=================================================================="
echo -e "${CYAN}💡 Quick Test Commands:${NC}"
echo "──────────────────────────────────────────────────────────────────"
echo ""
echo "# Test AI Runtime directly (no auth required):"
echo -e "${GREEN}curl -X POST http://localhost:8000/api/v1/chat \\${NC}"
echo -e "${GREEN}  -H 'Content-Type: application/json' \\${NC}"
echo -e "${GREEN}  -d '{\"session_id\": \"test\", \"message\": \"Hello!\", \"config\": {}}'${NC}"
echo ""

if [ "$GO_AVAILABLE" != "false" ]; then
    echo "# Login to Platform:"
    echo -e "${GREEN}curl -X POST http://localhost:8080/api/v1/auth/login \\${NC}"
    echo -e "${GREEN}  -H 'Content-Type: application/json' \\${NC}"
    echo -e "${GREEN}  -d '{\"email\": \"demo@example.com\", \"password\": \"demo123456\"}'${NC}"
    echo ""
fi

echo "=================================================================="
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"
echo ""

# Trap SIGINT and cleanup
cleanup() {
    echo ""
    echo "=================================================================="
    print_info "Shutting down services..."
    echo "=================================================================="

    if [ ! -z "$AI_RUNTIME_PID" ]; then
        print_info "Stopping AI Runtime (PID: $AI_RUNTIME_PID)..."
        kill $AI_RUNTIME_PID 2>/dev/null || true
    fi

    if [ ! -z "$PLATFORM_PID" ]; then
        print_info "Stopping Platform Layer (PID: $PLATFORM_PID)..."
        kill $PLATFORM_PID 2>/dev/null || true
    fi

    echo ""
    print_success "All services stopped"
    echo ""
    exit 0
}

trap cleanup INT TERM

# Wait for processes
wait