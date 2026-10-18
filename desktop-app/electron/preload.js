const { contextBridge, ipcRenderer } = require('electron');

// Expose protected methods to the renderer process
contextBridge.exposeInMainWorld('electronAPI', {
  // Backend URL
  getBackendUrl: () => ipcRenderer.invoke('get-backend-url'),
  
  // App info
  getAppVersion: () => ipcRenderer.invoke('get-app-version'),
  
  // Backend status
  getBackendStatus: () => ipcRenderer.invoke('get-backend-status'),
  
  // App control
  relaunch: () => ipcRenderer.invoke('relaunch'),
  quit: () => ipcRenderer.invoke('quit'),
  
  // Platform info
  platform: process.platform,
  isElectron: true
});
