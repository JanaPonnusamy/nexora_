// CommonJS preload (see main.cjs for why Electron 22 requires CJS here).
const { contextBridge, ipcRenderer } = require('electron');
const { createHash } = require('node:crypto');
const os = require('node:os');

const machineName = os.hostname();
const fingerprint = createHash('sha256')
  .update(`${machineName}|${os.platform()}|${os.arch()}|${os.userInfo().username}`)
  .digest('hex');

contextBridge.exposeInMainWorld('nexoraDesktop', {
  platform: process.platform,
  machineName,
  fingerprint,
  versions: {
    electron: process.versions.electron,
    chrome: process.versions.chrome,
    node: process.versions.node
  },
  isDev: () => ipcRenderer.invoke('dev:isDev'),
  setViewport: (width, height) => ipcRenderer.invoke('dev:setViewport', { width, height }),
  maximizeViewport: () => ipcRenderer.invoke('dev:maximizeViewport')
});
