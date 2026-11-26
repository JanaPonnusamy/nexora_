'use strict';

const { contextBridge, ipcRenderer } = require('electron');

// Inlined, not required from ../ipc/channels.cjs: a sandboxed preload
// (webPreferences.sandbox: true) runs in Electron's restricted preload
// context, which cannot resolve a relative require() to a sibling project
// file outside its own directory. Keep this list identical to
// electron/ipc/channels.cjs — the main process's registerHandlers.cjs is
// the source of truth; this is a literal copy for the sandboxed context.
const IPC_CHANNELS = Object.freeze({
  APP_GET_VERSION: 'app:getVersion',
  APP_GET_PLATFORM_INFO: 'app:getPlatformInfo',
  THEME_GET_NATIVE: 'theme:getNative',
  THEME_SET_PREFERENCE: 'theme:setPreference',
  HEALTH_CHECK: 'app:healthCheck',
  SESSION_GET: 'session:get',
  SESSION_SET: 'session:set',
  SESSION_CLEAR: 'session:clear',
  UI_SESSION_PATH: 'session:path',
  UI_SESSION_READ: 'session:read',
  UI_SESSION_WRITE: 'session:write',
  EXPORT_WRITE_FILE: 'export:writeFile',
  EXPORT_OPEN_PATH: 'export:openPath',
  EXPORT_CHOOSE_FOLDER: 'export:chooseFolder',
  ORDER_CACHE_READ: 'orderCache:read',
  ORDER_CACHE_WRITE: 'orderCache:write',
});

// Only these specific, named functions are exposed to the renderer.
// No generic ipcRenderer.invoke passthrough is exposed — every call here
// is a fixed channel from the allowlist, with no caller-supplied channel
// string, so the renderer cannot invoke an arbitrary IPC channel.
contextBridge.exposeInMainWorld('nextechMediq', {
  app: {
    getVersion: () => ipcRenderer.invoke(IPC_CHANNELS.APP_GET_VERSION),
    getPlatformInfo: () => ipcRenderer.invoke(IPC_CHANNELS.APP_GET_PLATFORM_INFO),
    healthCheck: () => ipcRenderer.invoke(IPC_CHANNELS.HEALTH_CHECK),
  },
  theme: {
    getNative: () => ipcRenderer.invoke(IPC_CHANNELS.THEME_GET_NATIVE),
    setPreference: (preference) => ipcRenderer.invoke(IPC_CHANNELS.THEME_SET_PREFERENCE, preference),
  },
  session: {
    get: () => ipcRenderer.invoke(IPC_CHANNELS.SESSION_GET),
    set: (session) => ipcRenderer.invoke(IPC_CHANNELS.SESSION_SET, session),
    clear: () => ipcRenderer.invoke(IPC_CHANNELS.SESSION_CLEAR),
  },
});

// Ported Order Workspace/Procurement code (OwExportKit.js etc., copied
// verbatim from supplier-stock-client) calls window.nexoraDesktop.* directly.
// Exposed as a second bridge, backed by the same main-process handlers
// registered above, so that code runs unmodified instead of silently
// no-op'ing into the browser-download/localStorage fallback paths.
contextBridge.exposeInMainWorld('nexoraDesktop', {
  readSession: (name) => ipcRenderer.invoke(IPC_CHANNELS.UI_SESSION_READ, name),
  writeSession: (name, data) => ipcRenderer.invoke(IPC_CHANNELS.UI_SESSION_WRITE, name, data),
  sessionPath: (name) => ipcRenderer.invoke(IPC_CHANNELS.UI_SESSION_PATH, name),
  writeExportFile: (absolutePath, contentBase64) =>
    ipcRenderer.invoke(IPC_CHANNELS.EXPORT_WRITE_FILE, { absolutePath, contentBase64 }),
  openExportPath: (absolutePath) => ipcRenderer.invoke(IPC_CHANNELS.EXPORT_OPEN_PATH, { absolutePath }),
  chooseExportFolder: (defaultPath) => ipcRenderer.invoke(IPC_CHANNELS.EXPORT_CHOOSE_FOLDER, { defaultPath }),
  orderCache: {
    read: (store) => ipcRenderer.invoke(IPC_CHANNELS.ORDER_CACHE_READ, store),
    write: (store, data) => ipcRenderer.invoke(IPC_CHANNELS.ORDER_CACHE_WRITE, store, data),
  },
});
