# Quick Start Guide

## One-Click Start

### Linux / Mac
```bash
./launch.sh
```

### Windows (Command Prompt)
```
launch.bat
```

### Windows (PowerShell)
```
.\launch.ps1
```

That's it! The application will:
1. Check prerequisites
2. Set up backend (Python)
3. Set up frontend (Node.js)
4. Start backend server
5. Start frontend server
6. Open your browser

## Prerequisites

- Python 3.11+
- Node.js 18+

## Troubleshooting

Run diagnostics:
```bash
./troubleshoot.sh
```

Common issues:
- **Port in use**: Stop any process using port 8000 or 5173
- **Missing Python**: Install from https://python.org
- **Missing Node.js**: Install from https://nodejs.org

## Manual Start

If the launcher doesn't work:

```bash
# Terminal 1: Backend
cd backend
source venv/bin/activate
uvicorn api.main:app --reload --port 8000

# Terminal 2: Frontend
cd frontend
npm run dev
```

Then open http://localhost:5173
