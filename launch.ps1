#==============================================================================
# AI Optical Design Engineer - Launcher Script (Windows PowerShell)
#==============================================================================

# Configuration
$BACKEND_PORT = 8000
$FRONTEND_PORT = 5173
$BACKEND_URL = "http://localhost:$BACKEND_PORT"
$FRONTEND_URL = "http://localhost:$FRONTEND_PORT"
$MAX_WAIT = 30

# Get script directory
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $SCRIPT_DIR

# Cleanup function
function Cleanup {
    Write-Host "`nShutting down..." -ForegroundColor Yellow
    if ($backendProcess -and !$backendProcess.HasExited) {
        $backendProcess.Kill()
    }
    if ($frontendProcess -and !$frontendProcess.HasExited) {
        $frontendProcess.Kill()
    }
    Write-Host "Shutdown complete" -ForegroundColor Green
    exit 0
}

# Trap Ctrl+C
[Console]::TreatControlCAsInput = $true

# Print banner
Write-Host "" -ForegroundColor Cyan
Write-Host "╔══════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║          AI Optical Design Engineer v0.2.0                   ║" -ForegroundColor Cyan
Write-Host "║          ═══════════════════════════════════════             ║" -ForegroundColor Cyan
Write-Host "║          Free, Professional Optical Design                   ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

#==============================================================================
# Check Prerequisites
#==============================================================================
Write-Host "Checking prerequisites..." -ForegroundColor Yellow

# Check Python
try {
    $pythonVersion = python --version 2>&1
    Write-Host "[OK] $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Python 3 not found" -ForegroundColor Red
    Write-Host "Please install Python 3.11+: https://python.org"
    exit 1
}

# Check Node.js
try {
    $nodeVersion = node --version
    Write-Host "[OK] Node.js $nodeVersion" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Node.js not found" -ForegroundColor Red
    Write-Host "Please install Node.js 18+: https://nodejs.org"
    exit 1
}

#==============================================================================
# Setup Backend
#==============================================================================
Write-Host "`nSetting up backend..." -ForegroundColor Yellow

Set-Location "$SCRIPT_DIR\backend"

# Create virtual environment if needed
if (-not (Test-Path "venv")) {
    Write-Host "Creating virtual environment..."
    python -m venv venv
}

# Activate virtual environment
& .\venv\Scripts\Activate.ps1

# Install dependencies if needed
try {
    python -c "import fastapi" 2>$null
} catch {
    Write-Host "Installing backend dependencies..."
    pip install -r requirements.txt
}

Write-Host "[OK] Backend ready" -ForegroundColor Green

#==============================================================================
# Setup Frontend
#==============================================================================
Write-Host "`nSetting up frontend..." -ForegroundColor Yellow

Set-Location "$SCRIPT_DIR\frontend"

# Install dependencies if needed
if (-not (Test-Path "node_modules")) {
    Write-Host "Installing frontend dependencies..."
    npm install
}

Write-Host "[OK] Frontend ready" -ForegroundColor Green

#==============================================================================
# Start Backend
#==============================================================================
Write-Host "`nStarting backend..." -ForegroundColor Yellow

Set-Location "$SCRIPT_DIR\backend"
& .\venv\Scripts\Activate.ps1

# Start backend
$backendProcess = Start-Process -FilePath "uvicorn" -ArgumentList "api.main:app","--host","0.0.0.0","--port","$BACKEND_PORT" -RedirectStandardOutput "backend.log" -RedirectStandardError "backend.log" -PassThru -NoNewWindow

# Wait for backend
Write-Host "Waiting for backend" -NoNewline
for ($i = 0; $i -lt $MAX_WAIT; $i++) {
    try {
        $response = Invoke-WebRequest -Uri "$BACKEND_URL/api/health" -TimeoutSec 1 -ErrorAction Stop
        if ($response.StatusCode -eq 200) {
            Write-Host "`n[OK] Backend ready" -ForegroundColor Green
            break
        }
    } catch {
        Write-Host "." -NoNewline
        Start-Sleep -Seconds 1
    }
    if ($i -eq $MAX_WAIT - 1) {
        Write-Host "`n[ERROR] Backend failed to start" -ForegroundColor Red
        Write-Host "Check log: backend.log"
        exit 1
    }
}

#==============================================================================
# Start Frontend
#==============================================================================
Write-Host "`nStarting frontend..." -ForegroundColor Yellow

Set-Location "$SCRIPT_DIR\frontend"

# Start frontend
$frontendProcess = Start-Process -FilePath "npm" -ArgumentList "run","dev" -RedirectStandardOutput "frontend.log" -RedirectStandardError "frontend.log" -PassThru -NoNewWindow

# Wait for frontend
Write-Host "Waiting for frontend" -NoNewline
for ($i = 0; $i -lt $MAX_WAIT; $i++) {
    try {
        $response = Invoke-WebRequest -Uri $FRONTEND_URL -TimeoutSec 1 -ErrorAction Stop
        if ($response.StatusCode -eq 200) {
            Write-Host "`n[OK] Frontend ready" -ForegroundColor Green
            break
        }
    } catch {
        Write-Host "." -NoNewline
        Start-Sleep -Seconds 1
    }
    if ($i -eq $MAX_WAIT - 1) {
        Write-Host "`n[ERROR] Frontend failed to start" -ForegroundColor Red
        Write-Host "Check log: frontend.log"
        exit 1
    }
}

#==============================================================================
# Open Browser
#==============================================================================
Write-Host "`n[OK] Application started successfully!" -ForegroundColor Green
Write-Host "`n  Backend:  $BACKEND_URL" -ForegroundColor Cyan
Write-Host "  Frontend: $FRONTEND_URL" -ForegroundColor Cyan
Write-Host "`n  Press Ctrl+C to stop`n"

# Open browser
Start-Sleep -Seconds 2
Start-Process $FRONTEND_URL

# Wait for Ctrl+C
while ($true) {
    if ([Console]::KeyAvailable) {
        $key = [Console]::ReadKey($true)
        if ($key.Key -eq "C" -and $key.Modifiers -eq "Control") {
            Cleanup
        }
    }
    Start-Sleep -Milliseconds 100
}
