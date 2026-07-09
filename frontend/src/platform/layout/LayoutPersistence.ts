const PREFIX = 'uninex.layout.'

/**
 * Generic localStorage-backed layout persistence for anything that isn't a
 * dock panel size (DockGroup already handles those via react-resizable-panels'
 * own useDefaultLayout). Used for open tabs, active module, nav state, etc. —
 * "users should return to exactly the same workspace after restarting."
 * Best-effort: localStorage can throw (quota, private-mode Safari, disabled
 * storage in some Electron configurations), and layout persistence should
 * never be why a module fails to load.
 */
export function saveLayout<T>(key: string, value: T): void {
  try {
    window.localStorage.setItem(PREFIX + key, JSON.stringify(value))
  } catch {
    // best-effort
  }
}

export function loadLayout<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(PREFIX + key)
    if (!raw) return fallback
    return JSON.parse(raw) as T
  } catch {
    return fallback
  }
}

export function clearLayout(key: string): void {
  try {
    window.localStorage.removeItem(PREFIX + key)
  } catch {
    // best-effort
  }
}
