import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import http from 'node:http';

// ESM `import` doesn't go through Electron's patched CommonJS `require`, so
// `import ... from 'electron'` only ever yields the path to the binary, not
// the app/BrowserWindow API. createRequire reaches the same patched require.
const require = createRequire(import.meta.url);
const { app, BrowserWindow, shell, ipcMain } = require('electron');

if (!app.isPackaged) {
  app.setPath('userData', path.join(app.getPath('temp'), 'nexora-supplier-stock-client-dev'));
}

app.commandLine.appendSwitch('disable-gpu');
app.commandLine.appendSwitch('disable-gpu-compositing');
app.commandLine.appendSwitch('disable-software-rasterizer');
app.disableHardwareAcceleration();

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const isDev = !app.isPackaged;

// "Stock Check" launch mode: same app, but a window locked to only the Stock
// Availability screen (plus Settings for first-run config). Resolved from, in
// order: the `--stock-only` CLI flag (dev), NEXORA_STOCK_ONLY=1, or a baked
// `nexoraMode: "stock"` in package.json (set by electron-builder's
// extraMetadata for the store-PC installer). The mode is handed to the renderer
// as a `?mode=stock` query param so App.jsx can trim its nav to match.
let bakedMode = '';
try { bakedMode = require(path.join(__dirname, '..', 'package.json')).nexoraMode || ''; } catch { /* dev */ }
const stockOnly = process.argv.includes('--stock-only')
  || process.env.NEXORA_STOCK_ONLY === '1'
  || bakedMode === 'stock';
const windowTitle = stockOnly ? 'Nexora Stock Check' : 'Nexora Supplier Stock';
const loadQuery = stockOnly ? { mode: 'stock' } : {};

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

async function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 980,
    minHeight: 680,
    title: windowTitle,
    backgroundColor: '#f5f7fb',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false
    }
  });

  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  win.once('ready-to-show', () => win.maximize());

  if (isDev) {
    const devPort = process.env.NEXORA_DEV_PORT || 5173;
    const useDevServer = await canReachDevServer(devPort);
    if (useDevServer) {
      const devUrl = new URL(`http://127.0.0.1:${devPort}`);
      if (stockOnly) devUrl.searchParams.set('mode', 'stock');
      win.webContents.session.clearCache().finally(() => {
        win.loadURL(devUrl.toString());
      });
      win.webContents.openDevTools({ mode: 'right' });
    } else {
      win.loadFile(path.join(__dirname, '..', 'dist', 'index.html'), { query: loadQuery });
    }
  } else {
    win.loadFile(path.join(__dirname, '..', 'dist', 'index.html'), { query: loadQuery });
  }
}

app.whenReady().then(() => {
  createWindow();

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
