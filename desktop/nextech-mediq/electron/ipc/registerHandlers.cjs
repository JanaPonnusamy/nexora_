'use strict';

const fs = require('fs');
const path = require('path');
const { ipcMain, nativeTheme, app, safeStorage, BrowserWindow, shell, dialog } = require('electron');
const { IPC_CHANNELS } = require('./channels.cjs');

// UI-state persistence (Order Workspace/Procurement export settings, etc.):
// one JSON file per name in userData, ported verbatim from
// supplier-stock-client/electron/main.cjs's sessionFilePath/session:read/write.
function uiSessionFilePath(name) {
  const safe = String(name || '').replace(/[^a-z0-9._-]/gi, '');
  if (!safe) return null;
  return path.join(app.getPath('userData'), safe);
}

// One file per store: userData/order_cache/order_cache_<STORE>.json.
function orderCacheFilePath(store) {
  const safe = String(store || '').trim().toUpperCase().replace(/[^A-Z0-9_-]/g, '_');
  if (!safe) return null;
  return path.join(app.getPath('userData'), 'order_cache', `order_cache_${safe}.json`);
}

function vaultPath() {
  return path.join(app.getPath('userData'), 'session.vault');
}

function readVault() {
  try {
    if (!safeStorage.isEncryptionAvailable()) return null;
    const file = vaultPath();
    if (!fs.existsSync(file)) return null;
    const json = safeStorage.decryptString(fs.readFileSync(file));
    const parsed = JSON.parse(json);
    if (!parsed || typeof parsed.token !== 'string' || !parsed.token) return null;
    return {
      token: parsed.token,
      user: parsed.user ?? null,
      loginDate: typeof parsed.loginDate === 'string' ? parsed.loginDate : '',
      expiresAt: typeof parsed.expiresAt === 'number' ? parsed.expiresAt : null,
      remember: parsed.remember !== false,
    };
  } catch {
    return null;
  }
}

function sessionForDisk(session) {
  if (!session || typeof session.token !== 'string' || !session.token || session.token.length > 16384) return null;
  return {
    token: session.token,
    user: session.user && typeof session.user === 'object' ? session.user : null,
    loginDate: typeof session.loginDate === 'string' ? session.loginDate : '',
    expiresAt: typeof session.expiresAt === 'number' ? session.expiresAt : null,
    remember: session.remember !== false,
  };
}

// Registers every IPC handler this app supports, keyed strictly by the
// channels.cjs allowlist. Called once from main/index.cjs after app.whenReady().
function registerIpcHandlers() {
  ipcMain.handle(IPC_CHANNELS.APP_GET_VERSION, () => app.getVersion());

  ipcMain.handle(IPC_CHANNELS.APP_GET_PLATFORM_INFO, () => ({
    platform: process.platform,
    arch: process.arch,
    electron: process.versions.electron,
    chrome: process.versions.chrome,
    node: process.versions.node,
  }));

  ipcMain.handle(IPC_CHANNELS.THEME_GET_NATIVE, () => ({
    shouldUseDarkColors: nativeTheme.shouldUseDarkColors,
    themeSource: nativeTheme.themeSource,
  }));

  ipcMain.handle(IPC_CHANNELS.THEME_SET_PREFERENCE, (_event, preference) => {
    const allowed = ['dark', 'light', 'system'];
    nativeTheme.themeSource = allowed.includes(preference) ? preference : 'system';
    return { themeSource: nativeTheme.themeSource };
  });

  ipcMain.handle(IPC_CHANNELS.HEALTH_CHECK, () => ({
    ok: true,
    timestamp: new Date().toISOString(),
  }));

  ipcMain.handle(IPC_CHANNELS.SESSION_GET, () => readVault());

  ipcMain.handle(IPC_CHANNELS.SESSION_SET, (_event, session) => {
    const payload = sessionForDisk(session);
    if (!payload || payload.remember === false) {
      try { fs.rmSync(vaultPath(), { force: true }); } catch { /* already gone */ }
      return { ok: Boolean(payload), encrypted: false };
    }
    if (!safeStorage.isEncryptionAvailable()) {
      return { ok: false, encrypted: false };
    }
    const encoded = safeStorage.encryptString(JSON.stringify(payload));
    fs.writeFileSync(vaultPath(), encoded);
    return { ok: true, encrypted: true };
  });

  ipcMain.handle(IPC_CHANNELS.SESSION_CLEAR, () => {
    try { fs.rmSync(vaultPath(), { force: true }); } catch { /* already gone */ }
    return { ok: true };
  });

  ipcMain.handle(IPC_CHANNELS.UI_SESSION_PATH, (_event, name) => uiSessionFilePath(name));

  ipcMain.handle(IPC_CHANNELS.UI_SESSION_READ, (_event, name) => {
    const file = uiSessionFilePath(name);
    if (!file) return null;
    try {
      return JSON.parse(fs.readFileSync(file, 'utf8'));
    } catch {
      return null; // missing or corrupt -> clean defaults
    }
  });

  ipcMain.handle(IPC_CHANNELS.UI_SESSION_WRITE, (_event, name, data) => {
    const file = uiSessionFilePath(name);
    if (!file) return false;
    try {
      fs.mkdirSync(path.dirname(file), { recursive: true });
      fs.writeFileSync(file, JSON.stringify(data, null, 2), 'utf8');
      return true;
    } catch {
      return false;
    }
  });

  ipcMain.handle(IPC_CHANNELS.ORDER_CACHE_READ, (_event, store) => {
    const file = orderCacheFilePath(store);
    if (!file) return null;
    try {
      return JSON.parse(fs.readFileSync(file, 'utf8'));
    } catch {
      return null;
    }
  });

  // Temp file + rename so a crash mid-write never leaves half a cache.
  ipcMain.handle(IPC_CHANNELS.ORDER_CACHE_WRITE, (_event, store, data) => {
    const file = orderCacheFilePath(store);
    if (!file) throw new Error('No store given.');
    fs.mkdirSync(path.dirname(file), { recursive: true });
    const tmp = `${file}.tmp`;
    fs.writeFileSync(tmp, JSON.stringify(data), 'utf8');
    fs.renameSync(tmp, file);
    return file;
  });

  // Writes base64 `content` to `absolutePath`, creating any missing parent
  // folders along the way. Returns the final path actually written.
  ipcMain.handle(IPC_CHANNELS.EXPORT_WRITE_FILE, (_event, { absolutePath, contentBase64 }) => {
    if (!absolutePath) throw new Error('No destination path given.');
    fs.mkdirSync(path.dirname(absolutePath), { recursive: true });
    fs.writeFileSync(absolutePath, Buffer.from(contentBase64, 'base64'));
    return absolutePath;
  });

  // Opens an exported file in its default app or an export folder in
  // Explorer. Restricted to known export extensions / directories so the
  // renderer can't use it to launch arbitrary executables.
  ipcMain.handle(IPC_CHANNELS.EXPORT_OPEN_PATH, async (_event, { absolutePath }) => {
    if (!absolutePath || !fs.existsSync(absolutePath)) return 'File not found.';
    const isDir = fs.statSync(absolutePath).isDirectory();
    if (!isDir && !/\.(xls|xlsx|csv)$/i.test(absolutePath)) return 'Unsupported file type.';
    return shell.openPath(absolutePath);
  });

  // Native "choose a folder" dialog, seeded at the operator's current
  // default so changing the export destination is a couple of clicks.
  ipcMain.handle(IPC_CHANNELS.EXPORT_CHOOSE_FOLDER, async (event, { defaultPath }) => {
    const win = BrowserWindow.fromWebContents(event.sender);
    const result = await dialog.showOpenDialog(win, {
      title: 'Choose export folder',
      defaultPath: defaultPath || undefined,
      properties: ['openDirectory', 'createDirectory']
    });
    if (result.canceled || !result.filePaths.length) return null;
    return result.filePaths[0];
  });
}

module.exports = { registerIpcHandlers };
