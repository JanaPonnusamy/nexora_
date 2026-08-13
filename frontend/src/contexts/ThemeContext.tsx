import { createContext, useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import type { Theme, ThemeContextValue, ThemePreference } from '../types/theme'
import { STORAGE_KEYS } from '../utils/storageKeys'
import { applyTheme, resolveTheme, watchSystemTheme } from '../design-system/applyTheme'

const PREFERENCES: readonly ThemePreference[] = ['light', 'dark', 'system']

function isPreference(value: unknown): value is ThemePreference {
  return typeof value === 'string' && (PREFERENCES as readonly string[]).includes(value)
}

function getInitialPreference(): ThemePreference {
  const saved = localStorage.getItem(STORAGE_KEYS.theme)
  return isPreference(saved) ? saved : 'system'
}

export const ThemeContext = createContext<ThemeContextValue | undefined>(undefined)

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreferenceState] = useState<ThemePreference>(getInitialPreference)
  // Mirrors the OS. Only the media-query subscription writes to it.
  const [systemTheme, setSystemTheme] = useState<Theme>(() => resolveTheme('system'))

  // Derived, not stored — the resolved theme is a pure function of the two
  // values above, so there is nothing to keep in sync.
  const theme: Theme = preference === 'system' ? systemTheme : preference

  useEffect(() => {
    applyTheme(theme)
  }, [theme])

  useEffect(() => {
    localStorage.setItem(STORAGE_KEYS.theme, preference)
  }, [preference])

  // Track the OS the whole time, not just while `system` is selected, so
  // switching back to `system` is already correct.
  useEffect(() => watchSystemTheme(setSystemTheme), [])

  const setPreference = useCallback((next: ThemePreference) => setPreferenceState(next), [])
  const setTheme = useCallback((next: Theme) => setPreferenceState(next), [])

  const cycleTheme = useCallback(() => {
    setPreferenceState((prev) => PREFERENCES[(PREFERENCES.indexOf(prev) + 1) % PREFERENCES.length])
  }, [])

  // Flips against what's on screen, so the first click always visibly changes
  // something even when the preference was `system`.
  const toggleTheme = useCallback(() => {
    setPreferenceState(theme === 'dark' ? 'light' : 'dark')
  }, [theme])

  const value = useMemo<ThemeContextValue>(
    () => ({ preference, theme, setPreference, setTheme, cycleTheme, toggleTheme }),
    [preference, theme, setPreference, setTheme, cycleTheme, toggleTheme],
  )

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}
