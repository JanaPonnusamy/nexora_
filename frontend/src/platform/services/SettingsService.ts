const PREFIX = 'uninex.settings.'

/**
 * Namespaced key/value storage for per-user preferences (default report date
 * range, grid page size, ...) — distinct from platform/layout/LayoutPersistence,
 * which is specifically for shell/workspace layout (tabs, dock sizes). Same
 * best-effort semantics: storage failures never bubble up to callers.
 */
export const settingsService = {
  get<T>(key: string, fallback: T): T {
    try {
      const raw = window.localStorage.getItem(PREFIX + key)
      if (raw === null) return fallback
      return JSON.parse(raw) as T
    } catch {
      return fallback
    }
  },
  set<T>(key: string, value: T): void {
    try {
      window.localStorage.setItem(PREFIX + key, JSON.stringify(value))
    } catch {
      // best-effort
    }
  },
  remove(key: string): void {
    try {
      window.localStorage.removeItem(PREFIX + key)
    } catch {
      // best-effort
    }
  },
}
