const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('settingsApi', {
  getConfig: () => ipcRenderer.invoke('qs:settings:get'),
  saveConfig: (patch) => ipcRenderer.invoke('qs:settings:save', patch),
  restart: () => ipcRenderer.send('qs:settings:restart'),
  close: () => ipcRenderer.send('qs:settings:close'),
});
