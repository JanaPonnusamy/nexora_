import { app, BrowserWindow, Menu, Tray, ipcMain, shell } from 'electron'
import path from 'node:path'
import fs from 'node:fs'
import log from 'electron-log/main'
import windowStateKeeper from 'electron-window-state'

log.initialize()
log.transports.file.level = 'info'
log.transports.console.level = app.isPackaged ? false : 'debug'

process.on('uncaughtException', (err) => {
  log.error('[main] uncaughtException', err)
})
process.on('unhandledRejection', (reason) => {
  log.error('[main] unhandledRejection', reason)
})

interface UniNexConfig {
  apiBase: string
  env: 'development' | 'production'
}

// Reads an optional uninex.config.json from the user's data dir so a packaged
// install can be pointed at a different HO server without rebuilding — same
// intent as the web deployment's server-injected /config.js.
function loadConfig(): UniNexConfig {
  const defaults: UniNexConfig = {
    apiBase: process.env.UNINEX_API_BASE || 'http://localhost:8000',
    env: app.isPackaged ? 'production' : 'development',
  }
  const configPath = path.join(app.getPath('userData'), 'uninex.config.json')
  try {
    if (fs.existsSync(configPath)) {
      const raw = JSON.parse(fs.readFileSync(configPath, 'utf-8'))
      return { ...defaults, ...raw }
    }
  } catch (err) {
    log.error('[main] failed to read uninex.config.json, using defaults', err)
  }
  return defaults
}

let mainWindow: BrowserWindow | null = null
let tray: Tray | null = null

function buildMenu() {
  const template: Electron.MenuItemConstructorOptions[] = [
    { label: 'File', submenu: [{ role: 'quit' }] },
    {
      label: 'Edit',
      submenu: [
        { role: 'undo' },
        { role: 'redo' },
        { type: 'separator' },
        { role: 'cut' },
        { role: 'copy' },
        { role: 'paste' },
      ],
    },
    {
      label: 'View',
      submenu: [
        { role: 'reload' },
        { role: 'forceReload' },
        { role: 'toggleDevTools' },
        { type: 'separator' },
        { role: 'resetZoom' },
        { role: 'zoomIn' },
        { role: 'zoomOut' },
        { type: 'separator' },
        { role: 'togglefullscreen' },
      ],
    },
    {
      label: 'Help',
      submenu: [
        {
          label: 'About UniNex',
          click: () => log.info(`[main] UniNex Desktop v${app.getVersion()}`),
        },
      ],
    },
  ]
  Menu.setApplicationMenu(Menu.buildFromTemplate(template))
}

// Tray icon slot — wired up but inert until an icon asset is added under
// electron/icons/; future modules/branding drop a file there, nothing else
// needs to change here.
function createTray() {
  const iconPath = path.join(__dirname, '../electron/icons/tray.png')
  if (!fs.existsSync(iconPath)) {
    log.info('[main] no tray icon asset found, skipping tray creation')
    return
  }
  tray = new Tray(iconPath)
  tray.setToolTip('UniNex Desktop')
  tray.setContextMenu(
    Menu.buildFromTemplate([
      { label: 'Show', click: () => mainWindow?.show() },
      { type: 'separator' },
      { role: 'quit' },
    ]),
  )
}

async function createWindow() {
  const config = loadConfig()

  const windowState = windowStateKeeper({ defaultWidth: 1440, defaultHeight: 900 })

  mainWindow = new BrowserWindow({
    x: windowState.x,
    y: windowState.y,
    width: windowState.width,
    height: windowState.height,
    minWidth: 1024,
    minHeight: 640,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      // Preload reads this before the renderer's scripts run and exposes it as
      // window.__UNINEX_API_BASE__ — apiClient.ts's existing runtime-override
      // resolution then needs zero Electron-specific code.
      additionalArguments: [`--uninex-config=${JSON.stringify(config)}`],
    },
  })

  windowState.manage(mainWindow)
  mainWindow.once('ready-to-show', () => mainWindow?.show())

  // Anything the renderer tries to open in a "new window" (target=_blank links,
  // window.open) goes to the OS browser instead of a second Electron window.
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: 'deny' }
  })

  mainWindow.on('closed', () => {
    mainWindow = null
  })

  const devServerUrl = process.env.VITE_DEV_SERVER_URL
  if (devServerUrl) {
    await mainWindow.loadURL(devServerUrl)
    mainWindow.webContents.openDevTools({ mode: 'detach' })
  } else {
    await mainWindow.loadFile(path.join(__dirname, '../dist/index.html'))
  }
}

// Renderer is asked to run each open module's saveState() before the process
// actually exits, and acks via 'app:quit-ready' once done. A hung or missing
// renderer listener must never block shutdown, hence the bounded fallback.
let quitAcknowledged = false
const QUIT_ACK_TIMEOUT_MS = 2000

ipcMain.on('app:quit-ready', () => {
  quitAcknowledged = true
  app.quit()
})

app.on('before-quit', (event) => {
  if (quitAcknowledged || !mainWindow) return
  event.preventDefault()
  mainWindow.webContents.send('app:before-quit')
  setTimeout(() => {
    quitAcknowledged = true
    app.quit()
  }, QUIT_ACK_TIMEOUT_MS)
})

ipcMain.on('shell:open-external', (_event, url: string) => {
  shell.openExternal(url)
})

ipcMain.on(
  'log:write',
  (_event, entry: { level: 'info' | 'warn' | 'error'; scope: string; message: string; data?: unknown }) => {
    const line = `[${entry.scope}] ${entry.message}`
    if (entry.level === 'error') log.error(line, entry.data ?? '')
    else if (entry.level === 'warn') log.warn(line, entry.data ?? '')
    else log.info(line, entry.data ?? '')
  },
)

ipcMain.handle('config:get', () => loadConfig())

function bootstrap() {
  const gotLock = app.requestSingleInstanceLock()
  if (!gotLock) {
    app.quit()
    return
  }

  app.on('second-instance', () => {
    if (!mainWindow) return
    if (mainWindow.isMinimized()) mainWindow.restore()
    mainWindow.focus()
  })

  app.whenReady().then(() => {
    buildMenu()
    createTray()
    createWindow()

    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) createWindow()
    })
  })

  app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit()
  })
}

bootstrap()
