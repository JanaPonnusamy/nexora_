// CommonJS entry point. Electron 22 (the last release supporting Windows 7/8)
// does not support ESM main-process entry points - that only arrived in
// Electron 28 - so the main and preload scripts are plain CommonJS. The
// renderer (dist/) is still an ES-module bundle loaded via file://, which is
// fine on Electron 22's Chromium.
const path = require('node:path');
const http = require('node:http');
const { app, BrowserWindow, shell, ipcMain } = require('electron');
const { autoUpdater } = require('electron-updater');

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
    title: 'Nexora Supplier Stock',
    backgroundColor: '#f5f7fb',
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
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
      win.webContents.session.clearCache().finally(() => {
        win.loadURL(`http://127.0.0.1:${devPort}`);
      });
      win.webContents.openDevTools({ mode: 'right' });
    } else {
      win.loadFile(path.join(__dirname, '..', 'dist', 'index.html'));
    }
  } else {
    win.loadFile(path.join(__dirname, '..', 'dist', 'index.html'));
  }
}

// Remote auto-update: on launch, check the HO update feed (configured via
// build.publish -> http://<HO>/updates), download a newer build silently, and
// install it the next time the app quits (autoInstallOnAppQuit). Store PCs are
// closed daily, so updates land without interrupting the user mid-session.
function initAutoUpdates() {
  if (!app.isPackaged) return;
  autoUpdater.autoDownload = true;
  autoUpdater.autoInstallOnAppQuit = true;
  autoUpdater.on('error', () => { /* offline / feed unreachable - ignore */ });
  autoUpdater.checkForUpdates().catch(() => {});
  // Re-check every 6 hours in case a PC stays on for days.
  setInterval(() => autoUpdater.checkForUpdates().catch(() => {}), 6 * 60 * 60 * 1000);
}

app.whenReady().then(() => {
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
