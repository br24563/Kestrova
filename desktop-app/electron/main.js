const { app, BrowserWindow, Tray, Menu, ipcMain, dialog, shell } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const axios = require('axios');

// Configuration
const BACKEND_PORT = 8000;
const BACKEND_URL = `http://localhost:${BACKEND_PORT}`;
const IS_DEV = process.env.NODE_ENV === 'development';

// Global state
let mainWindow = null;
let backendProcess = null;
let tray = null;
let isQuitting = false;

//==============================================================================
// Backend Management
//==============================================================================

function getBackendPath() {
  if (IS_DEV) {
    return path.join(__dirname, '../../backend');
  }
  return path.join(process.resourcesPath, 'backend');
}

function getPythonPath() {
  const backendPath = getBackendPath();
  if (process.platform === 'win32') {
    return path.join(backendPath, 'venv', 'Scripts', 'python.exe');
  }
  return path.join(backendPath, 'venv', 'bin', 'python');
}

async function startBackend() {
  if (IS_DEV) {
    console.log('Development mode - assuming backend is running separately');
    return true;
  }

  const backendPath = getBackendPath();
  const pythonPath = getPythonPath();

  // Check if backend exists
  if (!fs.existsSync(backendPath)) {
    dialog.showErrorBox(
      'Backend Not Found',
      'The optical engine backend was not found. Please reinstall the application.'
    );
    return false;
  }

  // Check if virtual environment exists
  if (!fs.existsSync(pythonPath)) {
    dialog.showErrorBox(
      'Python Not Found',
      'The bundled Python environment was not found. Please reinstall the application.'
    );
    return false;
  }

  return new Promise((resolve) => {
    console.log('Starting backend...');
    console.log('Backend path:', backendPath);
    console.log('Python path:', pythonPath);

    // Start uvicorn
    backendProcess = spawn(pythonPath, [
      '-m', 'uvicorn', 'api.main:app',
      '--host', '0.0.0.0',
      '--port', BACKEND_PORT.toString(),
      '--log-level', 'info'
    ], {
      cwd: backendPath,
      stdio: ['ignore', 'pipe', 'pipe']
    });

    backendProcess.stdout.on('data', (data) => {
      console.log(`Backend: ${data.toString().trim()}`);
    });

    backendProcess.stderr.on('data', (data) => {
      console.error(`Backend Error: ${data.toString().trim()}`);
    });

    backendProcess.on('error', (error) => {
      console.error('Failed to start backend:', error);
      dialog.showErrorBox(
        'Backend Error',
        `Failed to start the optical engine: ${error.message}`
      );
      resolve(false);
    });

    backendProcess.on('exit', (code) => {
      if (!isQuitting) {
        console.error(`Backend exited with code ${code}`);
        dialog.showErrorBox(
          'Backend Crashed',
          'The optical engine stopped unexpectedly. The application will now close.'
        );
        app.quit();
      }
    });

    // Wait for backend to be ready
    waitForBackend()
      .then(ready => {
        if (ready) {
          console.log('Backend is ready');
          resolve(true);
        } else {
          dialog.showErrorBox(
            'Backend Timeout',
            'The optical engine took too long to start. Please check the logs.'
          );
          resolve(false);
        }
      })
      .catch(error => {
        console.error('Error waiting for backend:', error);
        resolve(false);
      });
  });
}

async function waitForBackend(maxRetries = 30) {
  for (let i = 0; i < maxRetries; i++) {
    try {
      const response = await axios.get(`${BACKEND_URL}/api/health`, { timeout: 2000 });
      if (response.data.status === 'healthy') {
        return true;
      }
    } catch (error) {
      // Backend not ready yet
    }
    await new Promise(resolve => setTimeout(resolve, 1000));
  }
  return false;
}

function stopBackend() {
  if (backendProcess && !backendProcess.killed) {
    console.log('Stopping backend...');
    isQuitting = true;
    backendProcess.kill('SIGTERM');
    // Force kill after 5 seconds if still running
    setTimeout(() => {
      if (backendProcess && !backendProcess.killed) {
        backendProcess.kill('SIGKILL');
      }
    }, 5000);
  }
}

//==============================================================================
// Window Management
//==============================================================================

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    icon: path.join(__dirname, '../assets/icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: false
    },
    titleBarStyle: process.platform === 'darwin' ? 'hiddenInset' : 'default',
    show: false
  });

  // Load the app
  if (IS_DEV) {
    mainWindow.loadURL('http://localhost:5173');
    mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadURL(`${BACKEND_URL}`);
  }

  // Show window when ready to prevent visual flash
  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
    if (IS_DEV) {
      mainWindow.webContents.openDevTools();
    }
  });

  // Handle window close
  mainWindow.on('close', (event) => {
    if (!isQuitting && process.platform === 'darwin') {
      event.preventDefault();
      mainWindow.hide();
    }
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  // Handle external links
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });
}

//==============================================================================
// System Tray
//==============================================================================

function createTray() {
  const iconPath = path.join(__dirname, '../assets/icon-tray.png');
  
  // Use regular icon if tray icon doesn't exist
  const trayIcon = fs.existsSync(iconPath) ? iconPath : path.join(__dirname, '../assets/icon.png');
  
  tray = new Tray(trayIcon);
  tray.setToolTip('AI Optical Design Engineer');

  const contextMenu = Menu.buildFromTemplate([
    {
      label: 'Open',
      click: () => {
        if (mainWindow) {
          mainWindow.show();
        } else {
          createWindow();
        }
      }
    },
    { type: 'separator' },
    {
      label: 'Backend Status',
      enabled: false
    },
    {
      label: () => `Port: ${BACKEND_PORT}`,
      enabled: false
    },
    { type: 'separator' },
    {
      label: 'Quit',
      click: () => {
        isQuitting = true;
        app.quit();
      }
    }
  ]);

  tray.setContextMenu(contextMenu);

  tray.on('double-click', () => {
    if (mainWindow) {
      mainWindow.show();
    } else {
      createWindow();
    }
  });
}

//==============================================================================
// App Lifecycle
//==============================================================================

app.whenReady().then(async () => {
  // Start backend first
  const backendReady = await startBackend();
  
  if (!backendReady && !IS_DEV) {
    dialog.showErrorBox(
      'Startup Failed',
      'Could not start the optical engine. Please check the installation and try again.'
    );
    app.quit();
    return;
  }

  // Create window and tray
  createWindow();
  createTray();

  // Handle macOS activate
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
  isQuitting = true;
  stopBackend();
});

//==============================================================================
// IPC Handlers
//==============================================================================

ipcMain.handle('get-backend-url', () => BACKEND_URL);

ipcMain.handle('get-app-version', () => app.getVersion());

ipcMain.handle('get-backend-status', async () => {
  try {
    const response = await axios.get(`${BACKEND_URL}/api/health`, { timeout: 5000 });
    return { status: 'running', ...response.data };
  } catch (error) {
    return { status: 'stopped', error: error.message };
  }
});

ipcMain.handle('relaunch', () => {
  app.relaunch();
  app.quit();
});

ipcMain.handle('quit', () => {
  isQuitting = true;
  app.quit();
});
