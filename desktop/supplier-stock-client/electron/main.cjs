// CommonJS entry point. Electron 22 (the last release supporting Windows 7/8)
// does not support ESM main-process entry points - that only arrived in
// Electron 28 - so the main and preload scripts are plain CommonJS. The
// renderer (dist/) is still an ES-module bundle loaded via file://, which is
// fine on Electron 22's Chromium.
const path = require('node:path');
const http = require('node:http');
const fs = require('node:fs');
const { app, BrowserWindow, shell, ipcMain, nativeTheme, Menu } = require('electron');
// electron-updater's `autoUpdater` export is a lazy getter that constructs an
// NsisUpdater the first time it's touched -- requiring it (and destructuring
// autoUpdater out of it) at module load time can hang/throw before app is
// ready. Required lazily inside initAutoUpdates() instead, and wrapped so a
// broken updater never takes the whole app down with it (it's a background
// nicety, not core functionality).

if (!app.isPackaged) {
  app.setPath('userData', path.join(app.getPath('temp'), 'nexora-supplier-stock-client-dev'));
}

app.commandLine.appendSwitch('disable-gpu');
app.commandLine.appendSwitch('disable-gpu-compositing');
app.commandLine.appendSwitch('disable-software-rasterizer');
app.disableHardwareAcceleration();

const isDev = !app.isPackaged;

function canReachDevServer(port) {
  return new Promise((resolve) => {
    const req = http.get(
      {
        host: '127.0.0.1',
        port,
        path: '/',
        timeout: 1500,
      },
      (res) => {
        res.resume();
        resolve(res.statusCode >= 200 && res.statusCode < 500);
      }
    );
    req.on('timeout', () => {
      req.destroy();
      resolve(false);
    });
    req.on('error', () => resolve(false));
  });
}

ipcMain.handle('dev:isDev', () => isDev);

// --------------------------------------------------------------------------
// UI session persistence (Label Exporter, spec Parts 9-15).
// Exactly ONE file per named session, in the app's userData dir. UI state
// only — never product/review/business data (that lives in the backend DB).
// Every write overwrites the same file (no history). Reads tolerate a
// missing/corrupt file by returning null so the renderer falls back to
// clean defaults.
// --------------------------------------------------------------------------
function sessionFilePath(name) {
  const safe = String(name || '').replace(/[^a-z0-9._-]/gi, '');
  if (!safe) return null;
  return path.join(app.getPath('userData'), safe);
}

ipcMain.handle('session:path', (_event, name) => sessionFilePath(name));

ipcMain.handle('session:read', (_event, name) => {
  const file = sessionFilePath(name);
  if (!file) return null;
  try {
    const raw = fs.readFileSync(file, 'utf8');
    return JSON.parse(raw);
  } catch {
    return null; // missing or corrupt -> clean defaults
  }
});

ipcMain.handle('session:write', (_event, name, data) => {
  const file = sessionFilePath(name);
  if (!file) return false;
  try {
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, JSON.stringify(data, null, 2), 'utf8');
    return true;
  } catch {
    return false;
  }
});

ipcMain.handle('dev:setViewport', (event, { width, height }) => {
  if (!isDev) return;
  const win = BrowserWindow.fromWebContents(event.sender);
  if (!win) return;
  if (win.isMaximized()) win.unmaximize();
  win.setContentSize(width, height);
});

ipcMain.handle('dev:maximizeViewport', (event) => {
  const win = BrowserWindow.fromWebContents(event.sender);
  if (win) win.maximize();
});

ipcMain.handle('theme:setPreference', (event, { preference, resolvedTheme }) => {
  const nextPreference = ['light', 'dark'].includes(preference) ? preference : 'light';
  nativeTheme.themeSource = nextPreference;

  const win = BrowserWindow.fromWebContents(event.sender);
  if (win) win.setBackgroundColor(resolvedTheme === 'dark' ? '#0a0f17' : '#f4f6fa');
});

async function createWindow() {
  const win = new BrowserWindow({
    // Target display size: the app is designed for 1366x768. useContentSize
    // makes the WEB CONTENT exactly 1366x768 (the chrome/title bar is extra),
    // so the layout matches the design target on install. Resizable is left on
    // (default) so it still works on larger/smaller screens.
    width: 1366,
    height: 768,
    useContentSize: true,
    minWidth: 1024,
    minHeight: 700,
    center: true,
    title: 'Axythic Supplier Stock',
    backgroundColor: '#f5f7fb',
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false
    }
  });

  win.webContents.setWindowOpenHandler(({ url }) => {
    // window.open('', '_blank') (label-queue print sheet) resolves to
    // 'about:blank' — let that open as a real popup window instead of
    // routing it through shell.openExternal, which hands 'about:' off to
    // Windows and pops "Get an app to open this 'about' link". Only genuine
    // http(s) links should leave the app via the OS shell.
    if (/^https?:/i.test(url)) {
      shell.openExternal(url);
      return { action: 'deny' };
    }
    return { action: 'allow' };
  });

  // Open at the 1366x768 design size (centered) instead of maximizing, so the
  // installed app presents the intended layout. The user can still maximize.
  win.once('ready-to-show', () => win.show());

  if (isDev) {
    const devPort = process.env.NEXORA_DEV_PORT || 5173;
    const useDevServer = await canReachDevServer(devPort);
    if (useDevServer) {
      win.webContents.session.clearCache().finally(() => {
        win.loadURL(`http://127.0.0.1:${devPort}`);
      });
      // Detached (own window) rather than docked right: a right-docked panel
      // steals ~1/3 of the renderer width, which compressed the store grid and
      // clipped the Billing History columns during development. Detached keeps
      // devtools available without distorting the 1366-wide layout.
      // Detached DevTools creates another Chromium renderer and was being
      // opened on every development launch, even when nobody needed it. Keep
      // F12/Ctrl+Shift+I available and allow explicit opt-in for diagnostics.
      if (process.env.NEXORA_OPEN_DEVTOOLS === '1') {
        win.webContents.openDevTools({ mode: 'detach' });
      }
    } else {
      win.loadFile(path.join(__dirname, '..', 'dist', 'index.html'));
    }
  } else {
    win.loadFile(path.join(__dirname, '..', 'dist', 'index.html'));
  }
}

// Remote updates are now owned by the SYSTEM-level NexoraStockClientWatchdog
// service (store_agent_setup/stock_client_watchdog_service.py), NOT by the app
// updating itself. The watchdog polls HO for the version AUTHORIZED for this
// store, verifies the signed package (sha256 + Ed25519), closes this GUI, runs
// the installer, health-checks, and rolls back on failure -- a running app
// cannot safely replace itself, and self-install-on-quit gave HO no per-store
// authorization, no verification, and no rollback. electron-updater's
// self-install path is intentionally disabled; the dependency is kept only so
// older installs that still call this can no-op cleanly.
function initAutoUpdates() {
  // No-op by design. See the comment above: updates are handled out-of-process
  // by the watchdog service, with HO authorization + integrity + rollback.
}

app.whenReady().then(() => {
  // Drop the native menu bar (File/Edit/View/Window/Help). This is a
  // single-purpose kiosk-style app, and the menu bar ate ~20px of vertical
  // space at the top — enough that a maximized window on a 1366×768 laptop
  // clipped the last store row. DevTools stays reachable via F12/Ctrl+Shift+I.
  Menu.setApplicationMenu(null);
  createWindow();
  initAutoUpdates();

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
