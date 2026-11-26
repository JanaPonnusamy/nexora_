// Minimal Electron shell for Quick Stock: one window, no chrome, loads the
// authenticated /quick-stock-app page (LAN first, public port as fallback) --
// the same NexTech MedIQ web app, reached via a real Nexora login instead of
// the public /quick-stock kiosk's shared PIN. Deliberately has no renderer
// bundle of its own -- the page IS the app.
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const { app, BrowserWindow, Menu, ipcMain } = require('electron');

// Local config, read from (and, via Settings, written to) a file next to
// this install -- NOT bundled read-only into the app, so a site tech can
// change the HO address without a rebuild. Packaged: next to the real .exe.
// Unpackaged (`electron .` in dev): next to this project's own package.json,
// since app.getPath('exe') there points inside node_modules/electron/dist.
function configFilePath() {
  return app.isPackaged
    ? path.join(path.dirname(app.getPath('exe')), 'quick-stock-config.json')
    : path.join(__dirname, '..', 'quick-stock-config.json');
}

function readConfigFile() {
  try {
    const raw = fs.readFileSync(configFilePath(), 'utf8');
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function writeConfigFile(nextConfig) {
  fs.writeFileSync(configFilePath(), JSON.stringify(nextConfig, null, 2), 'utf8');
}

let CONFIG = readConfigFile();

// Kiosk PIN -- only meaningful if `path` below is pointed back at the public
// /quick-stock route (the PinGate screen there). The default /quick-stock-app
// route ignores this entirely: it uses the operator's real Nexora login
// (stored by the page itself, same as the web app) as its credential.
function readConfiguredPin() {
  const pin = typeof CONFIG?.pin === 'string' ? CONFIG.pin.trim() : '';
  return pin || null;
}

// Quick Stock path -- defaults to the authenticated /quick-stock-app route
// (real Nexora login, full RBAC). A site can repoint this at the public
// /quick-stock PIN kiosk instead via Settings, without a rebuild.
function readConfiguredPath() {
  const configPath = typeof CONFIG?.path === 'string' ? CONFIG.path.trim() : '';
  if (!configPath) return '/quick-stock-app';
  return configPath.startsWith('/') ? configPath : `/${configPath}`;
}

// HO base URLs (LAN + public), in priority order -- read from config so a
// site can repoint this shell without a rebuild. Falls back to the existing
// hardcoded defaults when the config has no `hoUrls`.
function readConfiguredHoUrls() {
  const list = Array.isArray(CONFIG?.hoUrls) ? CONFIG.hoUrls.filter((u) => typeof u === 'string' && u.trim()) : [];
  if (list.length) return list.map((u) => u.trim().replace(/\/$/, ''));
  return ['http://192.168.10.73:8000', 'http://122.252.246.181:8443'];
}

app.commandLine.appendSwitch('disable-gpu');
app.commandLine.appendSwitch('disable-gpu-compositing');
app.commandLine.appendSwitch('disable-software-rasterizer');
app.disableHardwareAcceleration();

// Ordered candidates: LAN HO first (fast, no internet needed on-site), then
// the public port as a fallback for anywhere off the store LAN. Same
// LAN-first convention as store_agent/config.py's HO_API_URLS. Priority:
// --ho=<base-url> CLI flag (dev/check builds only, e.g. pointing at .80
// before a feature ships to the real .73 build) > quick-stock-config.json's
// hoUrls/path > the hardcoded defaults.
const hoOverrideArg = process.argv.find((a) => a.startsWith('--ho='));
const QUICK_STOCK_PATH = readConfiguredPath();
const CANDIDATE_URLS = hoOverrideArg
  ? [`${hoOverrideArg.slice(5).replace(/\/$/, '')}${QUICK_STOCK_PATH}`]
  : readConfiguredHoUrls().map((base) => `${base}${QUICK_STOCK_PATH}`);

function probe(url) {
  return new Promise((resolve) => {
    let req;
    try {
      req = http.get(url, { timeout: 2500 }, (res) => {
        res.resume();
        resolve(res.statusCode >= 200 && res.statusCode < 500);
      });
    } catch {
      resolve(false);
      return;
    }
    req.on('timeout', () => { req.destroy(); resolve(false); });
    req.on('error', () => resolve(false));
  });
}

async function resolveUrl() {
  for (const url of CANDIDATE_URLS) {
    if (await probe(url)) return url;
  }
  return CANDIDATE_URLS[0]; // nothing reachable -- load it anyway, page shows its own network error
}

let mainWindow = null;
let settingsWindow = null;

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 760,
    minHeight: 560,
    title: 'NexTech Quick Stock',
    autoHideMenuBar: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
    },
  });

  const configuredPin = readConfiguredPin();
  if (configuredPin) {
    // Runs on every navigation, before the page's own scripts execute --
    // seeds the PIN the page already checks on mount, so PinGate never shows.
    // In production this value is a long random token (see build.js), not a
    // human-typed PIN -- the operator never sees or enters anything.
    mainWindow.webContents.on('dom-ready', () => {
      mainWindow.webContents
        .executeJavaScript(
          `try { window.localStorage.setItem('nexora_quick_stock_pin', ${JSON.stringify(configuredPin)}); } catch {}`
        )
        .catch(() => {});
    });
  }

  const url = await resolveUrl();
  await mainWindow.loadURL(url);

  mainWindow.on('closed', () => { mainWindow = null; });
}

// A tiny Settings window for the HO LAN/public addresses -- kept off the
// main window entirely (no visible button) and reached via the app menu
// (Alt to reveal it, since the main window hides its menu bar) or Ctrl+,
// so a site tech can repoint the app without reinstalling, but a counter
// operator never sees a way to open it by accident.
function openSettingsWindow() {
  if (settingsWindow) { settingsWindow.focus(); return; }
  settingsWindow = new BrowserWindow({
    width: 420,
    height: 360,
    resizable: false,
    minimizable: false,
    maximizable: false,
    title: 'Quick Stock Settings',
    parent: mainWindow || undefined,
    modal: Boolean(mainWindow),
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'settingsPreload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  settingsWindow.loadFile(path.join(__dirname, 'settings.html'));
  settingsWindow.on('closed', () => { settingsWindow = null; });
}

ipcMain.handle('qs:settings:get', () => ({
  hoUrls: readConfiguredHoUrls(),
}));

ipcMain.handle('qs:settings:save', (_event, patch) => {
  const next = { ...(CONFIG || {}), ...patch };
  writeConfigFile(next);
  CONFIG = next;
  return { ok: true };
});

ipcMain.on('qs:settings:restart', () => {
  app.relaunch();
  app.exit(0);
});

ipcMain.on('qs:settings:close', () => {
  if (settingsWindow) settingsWindow.close();
});

function buildAppMenu() {
  const template = [
    {
      label: 'Quick Stock',
      submenu: [
        { label: 'Settings…', accelerator: 'CmdOrCtrl+,', click: () => openSettingsWindow() },
        { type: 'separator' },
        { role: 'reload' },
        { role: 'quit' },
      ],
    },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

app.whenReady().then(() => {
  buildAppMenu();
  createWindow();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', () => {
  if (mainWindow === null) createWindow();
});
