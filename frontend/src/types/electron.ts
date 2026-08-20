// Ambient contract for the API electron/preload.ts exposes via contextBridge.
// window.__UNINEX_API_BASE__ is read by services/apiClient.ts (same mechanism
// as the web deployment's server-injected /config.js); window.uninex is only
// present when running inside the Electron shell.
export interface UniNexHostApi {
  env: 'development' | 'production'
  isElectron: true
  quit: () => void
  openExternal: (url: string) => void
  onBeforeQuit: (handler: () => void) => () => void
  log: {
    info: (scope: string, message: string, data?: unknown) => void
    warn: (scope: string, message: string, data?: unknown) => void
    error: (scope: string, message: string, data?: unknown) => void
  }
  secureStorage: {
    get: (key: string) => Promise<string | null>
    set: (key: string, value: string) => Promise<void>
  }
  /** Native OS folder picker — returns the chosen absolute path, or null if
   *  the user cancelled. Desktop-only (Purchase Manager Export Document). */
  pickFolder: () => Promise<string | null>
  /** Writes `data` directly to `folderPath/filename` via the main process —
   *  bypasses the browser download/Save-As flow entirely. */
  saveFile: (
    folderPath: string,
    filename: string,
    data: Uint8Array,
  ) => Promise<{ ok: boolean; path?: string; error?: string }>
}

declare global {
  interface Window {
    __UNINEX_API_BASE__?: string
    uninex?: UniNexHostApi
  }
}
