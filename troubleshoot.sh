#!/bin/bash
#==============================================================================
# AI Optical Design Engineer - Troubleshooting Script
#==============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${BLUE}"
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║          AI Optical Design Engineer - Diagnostics           ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

ERRORS=0
WARNINGS=0

#==============================================================================
# Check System
#==============================================================================
echo -e "\n${YELLOW}System Information:${NC}"
echo "  OS: $(uname -s) $(uname -r)"
echo "  Arch: $(uname -m)"
echo "  Date: $(date)"

#==============================================================================
# Check Python
#==============================================================================
echo -e "\n${YELLOW}Checking Python...${NC}"

if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1)
    echo -e "  ${GREEN}✓ $PYTHON_VERSION${NC}"
    
    # Check version >= 3.11
    PYTHON_MAJOR=$(python3 -c 'import sys; print(sys.version_info.major)')
    PYTHON_MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)')
    if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 11 ]); then
        echo -e "  ${RED}✗ Python 3.11+ required${NC}"
        ERRORS=$((ERRORS + 1))
    fi
else
    echo -e "  ${RED}✗ Python 3 not found${NC}"
    ERRORS=$((ERRORS + 1))
fi

#==============================================================================
# Check Node.js
#==============================================================================
echo -e "\n${YELLOW}Checking Node.js...${NC}"

if command -v node &> /dev/null; then
    NODE_VERSION=$(node --version)
    echo -e "  ${GREEN}✓ Node.js $NODE_VERSION${NC}"
    
    # Check version >= 18
    NODE_MAJOR=$(node -e 'process.versions.node.split(".")[0]')
    if [ "$NODE_MAJOR" -lt 18 ]; then
        echo -e "  ${RED}✗ Node.js 18+ required${NC}"
        ERRORS=$((ERRORS + 1))
    fi
else
    echo -e "  ${RED}✗ Node.js not found${NC}"
    ERRORS=$((ERRORS + 1))
fi

# Check npm
if command -v npm &> /dev/null; then
    echo -e "  ${GREEN}✓ npm $(npm --version)${NC}"
else
    echo -e "  ${RED}✗ npm not found${NC}"
    ERRORS=$((ERRORS + 1))
fi

#==============================================================================
# Check Backend
#==============================================================================
echo -e "\n${YELLOW}Checking Backend...${NC}"

cd "$SCRIPT_DIR/backend"

# Check virtual environment
if [ -d "venv" ]; then
    echo -e "  ${GREEN}✓ Virtual environment exists${NC}"
else
    echo -e "  ${YELLOW}⚠ Virtual environment not found (will be created)${NC}"
    WARNINGS=$((WARNINGS + 1))
fi

# Check Python packages
if [ -d "venv" ]; then
    source venv/bin/activate
    
    PACKAGES=('fastapi' 'uvicorn' 'numpy' 'scipy' 'pydantic')
    for pkg in "${PACKAGES[@]}"; do
        if python -c "import $pkg" 2>/dev/null; then
            echo -e "  ${GREEN}✓ $pkg${NC}"
        else
            echo -e "  ${RED}✗ $pkg not installed${NC}"
            ERRORS=$((ERRORS + 1))
        fi
    done
fi

#==============================================================================
# Check Frontend
#==============================================================================
echo -e "\n${YELLOW}Checking Frontend...${NC}"

cd "$SCRIPT_DIR/frontend"

# Check node_modules
if [ -d "node_modules" ]; then
    echo -e "  ${GREEN}✓ node_modules exists${NC}"
else
    echo -e "  ${YELLOW}⚠ node_modules not found (will be installed)${NC}"
    WARNINGS=$((WARNINGS + 1))
fi

#==============================================================================
# Check Ports
#==============================================================================
echo -e "\n${YELLOW}Checking Ports...${NC}"

if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo -e "  ${RED}✗ Port 8000 is in use${NC}"
    ERRORS=$((ERRORS + 1))
else
    echo -e "  ${GREEN}✓ Port 8000 available${NC}"
fi

if lsof -Pi :5173 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo -e "  ${RED}✗ Port 5173 is in use${NC}"
    ERRORS=$((ERRORS + 1))
else
    echo -e "  ${GREEN}✓ Port 5173 available${NC}"
fi

#==============================================================================
# Summary
#==============================================================================
echo -e "\n${BLUE}══════════════════════════════════════════════════════════════${NC}"

if [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}✓ All checks passed!${NC}"
    if [ $WARNINGS -gt 0 ]; then
        echo -e "${YELLOW}⚠ $WARNINGS warning(s) (non-critical)${NC}"
    fi
    echo -e "\nRun ${YELLOW}./launch.sh${NC} to start the application"
else
    echo -e "${RED}✗ $ERRORS error(s) found${NC}"
    echo -e "\nPlease fix the errors above before starting"
    exit 1
fi
