// Kestrova desktop app: starts the bundled optics backend (a frozen
// kestrova-server executable built with PyInstaller) on a free local port
// and shows the web interface it serves.
//
// Development (npm run dev): the backend runs from source on port 8000 with
// the Python on PATH (or $KESTROVA_PYTHON), and the window loads the Vite
// dev server, which proxies /api to it.

const { app, BrowserWindow, dialog, ipcMain, shell } = require('electron');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const IS_DEV = process.env.NODE_ENV === 'development';
const DEV_BACKEND_PORT = 8000;
const DEV_FRONTEND_URL = 'http://localhost:5173';
// First launch can be slow (macOS verifies the bundle; antivirus scans it).
const STARTUP_TIMEOUT_MS = 180000;

let mainWindow = null;
let backendProcess = null;
let backendUrl = null;
let quitting = false;

//==============================================================================
// Backend
//==============================================================================

function backendCommand() {
  if (IS_DEV) {
    const python =
      process.env.KESTROVA_PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
    const backendDir = path.join(__dirname, '..', '..', 'backend');
    return {
      command: python,
      args: [
        path.join(backendDir, 'kestrova_server.py'),
        '--port',
        String(DEV_BACKEND_PORT),
        '--parent-pid',
        String(process.pid),
      ],
      cwd: backendDir,
    };
  }
  const dir = path.join(process.resourcesPath, 'backend', 'kestrova-server');
  const exe = process.platform === 'win32' ? 'kestrova-server.exe' : 'kestrova-server';
  return {
    command: path.join(dir, exe),
    args: ['--port', '0', '--parent-pid', String(process.pid)],
    cwd: dir,
  };
}

function logFile() {
  return path.join(app.getPath('userData'), 'backend.log');
}

// Start the backend; resolves with its URL once it prints KESTROVA_PORT.
function startBackend() {
  return new Promise((resolve, reject) => {
    const { command, args, cwd } = backendCommand();
    if (!IS_DEV && !fs.existsSync(command)) {
      reject(new Error(`The optics engine is missing (${command}). Please reinstall Kestrova.`));
      return;
    }
    const log = fs.createWriteStream(logFile(), { flags: 'w' });
    backendProcess = spawn(command, args, {
      cwd,
      env: { ...process.env, KESTROVA_DATA_DIR: app.getPath('userData') },
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
    });
    const timer = setTimeout(
      () => reject(new Error(`The optics engine did not start. See ${logFile()}`)),
      STARTUP_TIMEOUT_MS
    );
    let buffered = '';
    backendProcess.stdout.on('data', (chunk) => {
      log.write(chunk);
      buffered += chunk.toString();
      const match = buffered.match(/KESTROVA_PORT=(\d+)/);
      if (match && !backendUrl) {
        clearTimeout(timer);
        backendUrl = `http://127.0.0.1:${match[1]}`;
        resolve(backendUrl);
      }
    });
    backendProcess.stderr.on('data', (chunk) => log.write(chunk));
    backendProcess.on('error', (err) => {
      clearTimeout(timer);
      reject(err);
    });
    backendProcess.on('exit', (code) => {
      clearTimeout(timer);
      log.end();
      if (!backendUrl) {
        reject(new Error(`The optics engine exited (code ${code}). See ${logFile()}`));
      } else if (!quitting) {
        dialog.showErrorBox(
          'Kestrova',
          `The optics engine stopped unexpectedly (code ${code}). See ${logFile()}`
        );
        app.quit();
      }
    });
  });
}

function stopBackend() {
  if (backendProcess && backendProcess.exitCode === null) {
    backendProcess.kill();
  }
}

//==============================================================================
// Window
//==============================================================================

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    title: 'Kestrova',
    icon: path.join(__dirname, '..', 'assets', 'icon.png'),
    backgroundColor: '#0f172a',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  mainWindow.loadFile(path.join(__dirname, '..', 'src', 'index.html'));
  // Links that leave the app open in the default browser.
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });
  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

function showApp() {
  if (!mainWindow) createWindow();
  const url = IS_DEV ? DEV_FRONTEND_URL : backendUrl;
  if (url) mainWindow.loadURL(url);
}

//==============================================================================
// Lifecycle
//==============================================================================

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.whenReady().then(async () => {
    createWindow(); // shows the loading screen
    try {
      await startBackend();
      showApp();
    } catch (err) {
      dialog.showErrorBox('Kestrova could not start', err.message);
      quitting = true;
      app.quit();
    }
  });

  app.on('activate', () => {
    // macOS: reopen the window from the dock
    if (!mainWindow && backendUrl) showApp();
  });

  app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit();
  });

  app.on('before-quit', () => {
    quitting = true;
    stopBackend();
  });
}

//==============================================================================
// IPC (see preload.js)
//==============================================================================

ipcMain.handle('get-backend-url', () => backendUrl);
ipcMain.handle('get-app-version', () => app.getVersion());
ipcMain.handle('get-log-path', () => logFile());
