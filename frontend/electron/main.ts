import path from 'node:path'
import fs from 'node:fs'
import { fileURLToPath } from 'node:url'
import { createRequire } from 'node:module'
import type { BrowserWindow as BrowserWindowType, Tray as TrayType } from 'electron'
import log from 'electron-log/main'
import windowStateKeeper from 'electron-window-state'

// The npm "electron" package only ever exports the path to the Electron
// binary (used by tooling to spawn it) — the real app/BrowserWindow/etc API
// is injected solely into Electron's patched CommonJS `require`, which ESM
// `import` does not go through. Use createRequire to reach that same require.
// (`import type` above is erased at compile time, so it never hits this issue.)
const require = createRequire(import.meta.url)
const { app, BrowserWindow, Menu, Tray, ipcMain, shell, dialog } = require('electron') as typeof import('electron')

// main.ts builds to genuine ESM (see vite.config.ts), so CommonJS's __dirname
// isn't available — derive the equivalent from import.meta.url instead.
const __dirname = path.dirname(fileURLToPath(import.meta.url))

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
    apiBase: process.env.UNINEX_API_BASE || 'http://122.252.246.181:8443',
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

let mainWindow: BrowserWindowType | null = null
let tray: TrayType | null = null

// A hung or missing renderer 'app:before-quit' listener must never block
// shutdown — this bounds how long a window's close waits for the renderer's
// save-state ack before closing anyway.
const QUIT_ACK_TIMEOUT_MS = 2000

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

  // Ask the renderer to save state before the window actually closes — this
  // must be intercepted at the WINDOW level, not app 'before-quit': by the
  // time 'window-all-closed'/'before-quit' fire from the normal OS close-
  // button path, this window's own 'closed' handler has already nulled out
  // `mainWindow`, so an app-level listener never sees a live window to send
  // to. Scoped per-window (not a module-level flag) so a window recreated
  // via 'activate' (macOS, after all windows closed) gets its own prompt.
  // The `ipcMain.once`/explicit removeListener pair avoids ever leaving a
  // stale 'app:quit-ready' listener registered after this window closes.
  const win = mainWindow
  let allowClose = false
  win.on('close', (event) => {
    if (allowClose) return
    event.preventDefault()
    win.webContents.send('app:before-quit')
    const onAck = () => {
      clearTimeout(timeoutId)
      allowClose = true
      win.close()
    }
    ipcMain.once('app:quit-ready', onAck)
    const timeoutId = setTimeout(() => {
      ipcMain.removeListener('app:quit-ready', onAck)
      allowClose = true
      win.close()
    }, QUIT_ACK_TIMEOUT_MS)
  })

  win.on('closed', () => {
    if (mainWindow === win) mainWindow = null
  })

  const devServerUrl = process.env.VITE_DEV_SERVER_URL
  if (devServerUrl) {
    await mainWindow.loadURL(devServerUrl)
    mainWindow.webContents.openDevTools({ mode: 'detach' })
  } else {
    await mainWindow.loadFile(path.join(__dirname, '../dist/index.html'))
  }
}

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

// Export Document "save straight to a folder" (Purchase Manager) — a native
// folder picker plus a direct filesystem write, so the desktop app never
// routes an export through the browser's Downloads folder/Save-As prompt.
ipcMain.handle('dialog:pick-folder', async () => {
  if (!mainWindow) return null
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory', 'createDirectory'],
  })
  if (result.canceled || result.filePaths.length === 0) return null
  return result.filePaths[0]
})

ipcMain.handle(
  'fs:save-file',
  async (_event, folderPath: string, filename: string, data: Uint8Array) => {
    try {
      if (!fs.existsSync(folderPath)) fs.mkdirSync(folderPath, { recursive: true })
      const fullPath = path.join(folderPath, filename)
      fs.writeFileSync(fullPath, Buffer.from(data))
      return { ok: true, path: fullPath }
    } catch (err) {
      log.error('[main] fs:save-file failed', err)
      return { ok: false, error: err instanceof Error ? err.message : String(err) }
    }
  },
)

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
