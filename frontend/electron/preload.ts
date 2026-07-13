import { contextBridge, ipcRenderer } from 'electron'

interface UniNexConfig {
  apiBase: string
  env: 'development' | 'production'
}

const CONFIG_ARG_PREFIX = '--uninex-config='

function readInjectedConfig(): UniNexConfig {
  const raw = process.argv.find((arg) => arg.startsWith(CONFIG_ARG_PREFIX))
  const fallback: UniNexConfig = { apiBase: 'http://localhost:8000', env: 'development' }
  if (!raw) return fallback
  try {
    return JSON.parse(raw.slice(CONFIG_ARG_PREFIX.length)) as UniNexConfig
  } catch {
    return fallback
  }
}

const config = readInjectedConfig()

// Same global apiClient.ts already reads for the web deployment's server-
// injected /config.js — exposing it here means the API client layer needs no
// Electron-specific branch at all.
contextBridge.exposeInMainWorld('__UNINEX_API_BASE__', config.apiBase)

contextBridge.exposeInMainWorld('uninex', {
  env: config.env,
  isElectron: true,

  quit: () => ipcRenderer.send('app:quit-ready'),
  openExternal: (url: string) => ipcRenderer.send('shell:open-external', url),

  // Main sends this before it actually quits so open modules get a chance to
  // saveState(); the renderer must call quit() once done, or main's bounded
  // timeout force-quits after 2s so a hung listener can't block shutdown.
  onBeforeQuit: (handler: () => void) => {
    const listener = () => handler()
    ipcRenderer.on('app:before-quit', listener)
    return () => {
      ipcRenderer.removeListener('app:before-quit', listener)
    }
  },

  log: {
    info: (scope: string, message: string, data?: unknown) =>
      ipcRenderer.send('log:write', { level: 'info', scope, message, data }),
    warn: (scope: string, message: string, data?: unknown) =>
      ipcRenderer.send('log:write', { level: 'warn', scope, message, data }),
    error: (scope: string, message: string, data?: unknown) =>
      ipcRenderer.send('log:write', { level: 'error', scope, message, data }),
  },

  // Export Document "save straight to a folder" (Purchase Manager) — native
  // OS folder picker + a direct filesystem write, so a desktop export never
  // touches the browser Downloads folder or a Save-As prompt.
  pickFolder: (): Promise<string | null> => ipcRenderer.invoke('dialog:pick-folder'),
  saveFile: (
    folderPath: string,
    filename: string,
    data: Uint8Array,
  ): Promise<{ ok: boolean; path?: string; error?: string }> =>
    ipcRenderer.invoke('fs:save-file', folderPath, filename, data),

  // Placeholder for when real authentication lands (today the backend issues
  // no token to persist — see auth exploration). Keeps the host's contract
  // stable so a future auth implementation doesn't need a preload API change.
  secureStorage: {
    // eslint-disable-next-line @typescript-eslint/no-unused-vars -- placeholder signature, see comment above
    get: (_key: string): Promise<string | null> => Promise.resolve(null),
    // eslint-disable-next-line @typescript-eslint/no-unused-vars -- placeholder signature, see comment above
    set: (_key: string, _value: string): Promise<void> => Promise.resolve(),
  },
})
