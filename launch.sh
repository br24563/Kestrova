#!/bin/bash
#==============================================================================
# AI Optical Design Engineer - Launcher Script (Linux/Mac)
#==============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
BACKEND_PORT=8000
FRONTEND_PORT=5173
BACKEND_URL="http://localhost:${BACKEND_PORT}"
FRONTEND_URL="http://localhost:${FRONTEND_PORT}"
MAX_WAIT=30

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Cleanup function
cleanup() {
    echo -e "\n${YELLOW}Shutting down...${NC}"
    if [ -n "$BACKEND_PID" ] && kill -0 $BACKEND_PID 2>/dev/null; then
        kill $BACKEND_PID 2>/dev/null || true
        wait $BACKEND_PID 2>/dev/null || true
    fi
    if [ -n "$FRONTEND_PID" ] && kill -0 $FRONTEND_PID 2>/dev/null; then
        kill $FRONTEND_PID 2>/dev/null || true
        wait $FRONTEND_PID 2>/dev/null || true
    fi
    echo -e "${GREEN}✓ Shutdown complete${NC}"
    exit 0
}

# Trap signals
trap cleanup SIGINT SIGTERM EXIT

# Print banner
echo -e "${BLUE}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║          AI Optical Design Engineer v0.2.0                   ║"
echo "║          ═══════════════════════════════════════             ║"
echo "║          Free, Professional Optical Design                   ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

#==============================================================================
# Check Prerequisites
#==============================================================================
echo -e "${YELLOW}Checking prerequisites...${NC}"

# Check Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}✗ Python 3 not found${NC}"
    echo "Please install Python 3.11+: https://python.org"
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo -e "${GREEN}✓ Python ${PYTHON_VERSION}${NC}"

# Check Node.js
if ! command -v node &> /dev/null; then
    echo -e "${RED}✗ Node.js not found${NC}"
    echo "Please install Node.js 18+: https://nodejs.org"
    exit 1
fi

NODE_VERSION=$(node --version)
echo -e "${GREEN}✓ Node.js ${NODE_VERSION}${NC}"

# Check npm
if ! command -v npm &> /dev/null; then
    echo -e "${RED}✗ npm not found${NC}"
    exit 1
fi
echo -e "${GREEN}✓ npm $(npm --version)${NC}"

#==============================================================================
# Setup Backend
#==============================================================================
echo -e "\n${YELLOW}Setting up backend...${NC}"

cd "$SCRIPT_DIR/backend"

# Create virtual environment if needed
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies if needed
if ! python -c "import fastapi" 2>/dev/null; then
    echo "Installing backend dependencies..."
    pip install -r requirements.txt
fi

echo -e "${GREEN}✓ Backend ready${NC}"

#==============================================================================
# Setup Frontend
#==============================================================================
echo -e "\n${YELLOW}Setting up frontend...${NC}"

cd "$SCRIPT_DIR/frontend"

# Install dependencies if needed
if [ ! -d "node_modules" ]; then
    echo "Installing frontend dependencies..."
    npm install
fi

echo -e "${GREEN}✓ Frontend ready${NC}"

#==============================================================================
# Start Backend
#==============================================================================
echo -e "\n${YELLOW}Starting backend...${NC}"

cd "$SCRIPT_DIR/backend"
source venv/bin/activate

# Start backend in background
uvicorn api.main:app --host 0.0.0.0 --port $BACKEND_PORT > /tmp/aioe-backend.log 2>&1 &
BACKEND_PID=$!

echo "Backend PID: $BACKEND_PID"

# Wait for backend to be ready
echo -n "Waiting for backend"
for i in $(seq 1 $MAX_WAIT); do
    if curl -s "$BACKEND_URL/api/health" > /dev/null 2>&1; then
        echo -e "\n${GREEN}✓ Backend ready${NC}"
        break
    fi
    if [ $i -eq $MAX_WAIT ]; then
        echo -e "\n${RED}✗ Backend failed to start${NC}"
        echo "Check log: /tmp/aioe-backend.log"
        exit 1
    fi
    echo -n "."
    sleep 1
done

#==============================================================================
# Start Frontend
#==============================================================================
echo -e "\n${YELLOW}Starting frontend...${NC}"

cd "$SCRIPT_DIR/frontend"

# Start frontend in background
npm run dev > /tmp/aioe-frontend.log 2>&1 &
FRONTEND_PID=$!

echo "Frontend PID: $FRONTEND_PID"

# Wait for frontend to be ready
echo -n "Waiting for frontend"
for i in $(seq 1 $MAX_WAIT); do
    if curl -s "$FRONTEND_URL" > /dev/null 2>&1; then
        echo -e "\n${GREEN}✓ Frontend ready${NC}"
        break
    fi
    if [ $i -eq $MAX_WAIT ]; then
        echo -e "\n${RED}✗ Frontend failed to start${NC}"
        echo "Check log: /tmp/aioe-frontend.log"
        exit 1
    fi
    echo -n "."
    sleep 1
done

#==============================================================================
# Open Browser
#==============================================================================
echo -e "\n${GREEN}✓ Application started successfully!${NC}"
echo -e "\n  Backend:  ${BLUE}$BACKEND_URL${NC}"
echo -e "  Frontend: ${BLUE}$FRONTEND_URL${NC}"
echo -e "\n  Press Ctrl+C to stop\n"

# Open browser
sleep 1
if command -v xdg-open &> /dev/null; then
    xdg-open "$FRONTEND_URL" 2>/dev/null || true
elif command -v open &> /dev/null; then
    open "$FRONTEND_URL" 2>/dev/null || true
fi

# Wait for interrupt
wait
