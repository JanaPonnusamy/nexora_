'use strict';

const path = require('path');
const { app, BrowserWindow, shell } = require('electron');
const { secureWebPreferences, isNavigationAllowed } = require('../security/windowDefaults.cjs');
const { registerIpcHandlers } = require('../ipc/registerHandlers.cjs');

if (!app.isPackaged) {
  app.setPath('userData', path.join(app.getPath('temp'), 'nextech-mediq-dev'));
}

app.commandLine.appendSwitch('disable-gpu');
app.commandLine.appendSwitch('disable-gpu-compositing');
app.commandLine.appendSwitch('disable-software-rasterizer');
app.disableHardwareAcceleration();

const isDev = !app.isPackaged;
const DEV_SERVER_URL = process.env.NEXTECH_DEV_SERVER_URL || 'http://127.0.0.1:5183';

let mainWindow = null;

function createMainWindow() {
  const win = new BrowserWindow({
    width: 1366,
    height: 768,
    minWidth: 1024,
    minHeight: 640,
    show: false,
    autoHideMenuBar: true,
    backgroundColor: '#0B1220',
    icon: path.join(__dirname, '..', '..', 'src', 'assets', 'branding', 'icon.ico'),
    webPreferences: secureWebPreferences(path.join(__dirname, '..', 'preload', 'index.cjs')),
  });

  // Default every fresh launch to a maximized framed window. maximize()
  // keeps the Windows title bar and min/max/close controls; it is not
  // fullscreen. No saved bounds are applied, so a previous restore cannot
  // override this startup state. The user can still restore afterwards.
  win.once('ready-to-show', () => {
    if (win.isDestroyed()) return;
    win.maximize();
    win.show();
  });

  // Fallback: if ready-to-show is delayed or missed, ensure window is shown
  setTimeout(() => {
    if (!win.isDestroyed() && !win.isVisible()) {
      win.maximize();
      win.show();
    }
  }, 2000);

  win.webContents.on('did-fail-load', (event, errorCode, errorDescription, validatedURL) => {
    console.error(`[Electron] Failed to load ${validatedURL}: ${errorDescription} (${errorCode})`);
  });

  // Hard navigation/window-open allowlist — no arbitrary external URLs,
  // per Phase 2 §6 and the Phase 7 Quick Stock constraint ("do not load
  // arbitrary external URLs").
  win.webContents.on('will-navigate', (event, url) => {
    if (!isNavigationAllowed(url) && !url.startsWith(isDev ? DEV_SERVER_URL : 'file://')) {
      event.preventDefault();
    }
  });
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (isNavigationAllowed(url)) {
      shell.openExternal(url);
    }
    return { action: 'deny' };
  });

  if (isDev) {
    win.loadURL(DEV_SERVER_URL);
  } else {
    win.loadFile(path.join(__dirname, '..', '..', 'dist', 'index.html'));
  }

  return win;
}

const gotSingleInstanceLock = app.requestSingleInstanceLock();

if (!gotSingleInstanceLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    const win = mainWindow;
    if (!win || win.isDestroyed()) return;
    if (win.isMinimized()) win.restore();
    win.show();
    win.focus();
  });

  app.whenReady().then(() => {
    registerIpcHandlers();
    mainWindow = createMainWindow();

    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) {
        mainWindow = createMainWindow();
      }
    });
  });
}

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
