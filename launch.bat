@echo off
REM ==============================================================================
REM AI Optical Design Engineer - Launcher Script (Windows)
REM ==============================================================================

setlocal enabledelayedexpansion

REM Configuration
set BACKEND_PORT=8000
set FRONTEND_PORT=5173
set BACKEND_URL=http://localhost:%BACKEND_PORT%
set FRONTEND_URL=http://localhost:%FRONTEND_PORT%
set MAX_WAIT=30

REM Get script directory
set SCRIPT_DIR=%~dp0
cd /d %SCRIPT_DIR%

REM Print banner
echo.
echo ================================================================================
echo           AI Optical Design Engineer v0.2.0
echo           ===================================
echo           Free, Professional Optical Design
echo ================================================================================
echo.

REM ==============================================================================
REM Check Prerequisites
REM ================================================================================
echo Checking prerequisites...

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python 3 not found
    echo Please install Python 3.11+: https://python.org
    pause
    exit /b 1
)
for /f "tokens=2" %%i in ('python --version') do set PYTHON_VERSION=%%i
echo [OK] Python %PYTHON_VERSION%

REM Check Node.js
node --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js not found
    echo Please install Node.js 18+: https://nodejs.org
    pause
    exit /b 1
)
for /f "tokens=1" %%i in ('node --version') do set NODE_VERSION=%%i
echo [OK] Node.js %NODE_VERSION%

REM Check npm
npm --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] npm not found
    pause
    exit /b 1
)
echo [OK] npm

REM ==============================================================================
REM Setup Backend
REM ================================================================================
echo.
echo Setting up backend...

cd "%SCRIPT_DIR%backend"

REM Create virtual environment if needed
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Install dependencies if needed
python -c "import fastapi" >nul 2>&1
if errorlevel 1 (
    echo Installing backend dependencies...
    pip install -r requirements.txt
)

echo [OK] Backend ready

REM ==============================================================================
REM Setup Frontend
REM ================================================================================
echo.
echo Setting up frontend...

cd "%SCRIPT_DIR%frontend"

REM Install dependencies if needed
if not exist "node_modules" (
    echo Installing frontend dependencies...
    npm install
)

echo [OK] Frontend ready

REM ==============================================================================
REM Start Backend
REM ================================================================================
echo.
echo Starting backend...

cd "%SCRIPT_DIR%backend"
call venv\Scripts\activate.bat

REM Start backend in background
start "AI Optical Backend" cmd /c "uvicorn api.main:app --host 0.0.0.0 --port %BACKEND_PORT% ^> backend.log 2^>^&1"

REM Wait for backend to be ready
echo Waiting for backend...
for /L %%i in (1,1,%MAX_WAIT%) do (
    curl -s "%BACKEND_URL%/api/health" >nul 2>&1
    if not errorlevel 1 goto :backend_ready
    timeout /t 1 /nobreak >nul
)
echo [ERROR] Backend failed to start
pause
exit /b 1
:backend_ready
echo [OK] Backend ready

REM ==============================================================================
REM Start Frontend
REM ================================================================================
echo.
echo Starting frontend...

cd "%SCRIPT_DIR%frontend"

REM Start frontend in background
start "AI Optical Frontend" cmd /c "npm run dev ^> frontend.log 2^>^&1"

REM Wait for frontend to be ready
echo Waiting for frontend...
for /L %%i in (1,1,%MAX_WAIT%) do (
    curl -s "%FRONTEND_URL%" >nul 2>&1
    if not errorlevel 1 goto :frontend_ready
    timeout /t 1 /nobreak >nul
)
echo [ERROR] Frontend failed to start
pause
exit /b 1
:frontend_ready
echo [OK] Frontend ready

REM ==============================================================================
REM Open Browser
REM ================================================================================
echo.
echo [OK] Application started successfully!
echo.
echo   Backend:  %BACKEND_URL%
echo   Frontend: %FRONTEND_URL%
echo.
echo   Press any key to stop...

REM Open browser
timeout /t 2 /nobreak >nul
start %FRONTEND_URL%

REM Wait for user to press a key
pause >nul

REM Cleanup
echo.
echo Shutting down...
taskkill /FI "WINDOWTITLE eq AI Optical Backend" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq AI Optical Frontend" /F >nul 2>&1
echo [OK] Shutdown complete
