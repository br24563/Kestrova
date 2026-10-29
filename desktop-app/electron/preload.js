const { contextBridge, ipcRenderer } = require('electron');

// What the web interface can ask the desktop shell (see main.js).
contextBridge.exposeInMainWorld('electronAPI', {
  getBackendUrl: () => ipcRenderer.invoke('get-backend-url'),
  getAppVersion: () => ipcRenderer.invoke('get-app-version'),
  getLogPath: () => ipcRenderer.invoke('get-log-path'),
  platform: process.platform,
  isElectron: true,
});
