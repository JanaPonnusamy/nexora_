/** The theme actually being rendered. */
export type Theme = 'light' | 'dark'

/** What the user chose. `system` follows the OS and keeps following it. */
export type ThemePreference = Theme | 'system'

export interface ThemeContextValue {
  /** The user's choice, including `system`. */
  preference: ThemePreference
  /** The resolved theme on screen right now — never `system`. */
  theme: Theme
  setPreference: (preference: ThemePreference) => void
  /** Pin an explicit theme. Equivalent to `setPreference(theme)`. */
  setTheme: (theme: Theme) => void
  /** Cycle light -> dark -> system. */
  cycleTheme: () => void
  /** Flip between light and dark, dropping `system`. */
  toggleTheme: () => void
}
