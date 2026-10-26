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
  maximizeViewport: () => ipcRenderer.invoke('dev:maximizeViewport'),
  setTheme: (preference, resolvedTheme) => ipcRenderer.invoke('theme:setPreference', { preference, resolvedTheme }),
  // UI session persistence (one JSON file per name, in userData). UI state only.
  readSession: (name) => ipcRenderer.invoke('session:read', name),
  writeSession: (name, data) => ipcRenderer.invoke('session:write', name, data),
  sessionPath: (name) => ipcRenderer.invoke('session:path', name),
  // Order Workspace export-to-disk.
  writeExportFile: (absolutePath, contentBase64) => ipcRenderer.invoke('export:writeFile', { absolutePath, contentBase64 }),
  openExportPath: (absolutePath) => ipcRenderer.invoke('export:openPath', { absolutePath }),
  chooseExportFolder: (defaultPath) => ipcRenderer.invoke('export:chooseFolder', { defaultPath }),
  // This store PC's own WhatsApp (electron/whatsapp.cjs).
  whatsapp: {
    status: () => ipcRenderer.invoke('wa:status'),
    enable: () => ipcRenderer.invoke('wa:enable'),
    disable: () => ipcRenderer.invoke('wa:disable'),
    show: () => ipcRenderer.invoke('wa:show'),
    unlink: () => ipcRenderer.invoke('wa:unlink'),
    send: (payload) => ipcRenderer.invoke('wa:send', payload),
    log: () => ipcRenderer.invoke('wa:log'),
    // { query?, filter?: 'all'|'groups'|'contacts', refresh? } -> { chats: [{ name, kind }], error? }
    chats: (opts) => ipcRenderer.invoke('wa:chats', opts),
    readFiles: (paths) => ipcRenderer.invoke('wa:readFiles', paths)
  }
});
