/**
 * Applies the tokens from `tokens/theme.ts` to the live document.
 *
 * This runs before React's first paint (it is imported from `main.tsx`), so
 * there is no flash of an unstyled or wrong-theme shell.
 */
import { rootVariables, type ThemeName } from './tokens/theme'
import { STORAGE_KEYS } from '../utils/storageKeys'

/** What the user picked. `system` follows the OS and keeps following it. */
export type ThemePreference = ThemeName | 'system'

const DARK_QUERY = '(prefers-color-scheme: dark)'

/** Resolve a preference to the theme actually being rendered. */
export function resolveTheme(preference: ThemePreference): ThemeName {
  if (preference !== 'system') return preference
  if (typeof window === 'undefined' || !window.matchMedia) return 'light'
  return window.matchMedia(DARK_QUERY).matches ? 'dark' : 'light'
}

/**
 * Write every token onto `:root` and flag the theme for CSS that keys off it.
 *
 * `data-bs-theme` stays because Bootstrap's own component CSS keys off it;
 * `color-scheme` makes native scrollbars, form controls and the Electron
 * window chrome follow the theme too.
 */
export function applyTheme(name: ThemeName): void {
  if (typeof document === 'undefined') return

  const root = document.documentElement
  const style = root.style

  for (const [property, value] of Object.entries(rootVariables(name))) {
    style.setProperty(property, value)
  }

  root.setAttribute('data-bs-theme', name)
  root.setAttribute('data-theme', name)
  style.setProperty('color-scheme', name)
}

/**
 * Paint the stored theme onto the document before React mounts.
 *
 * `ThemeProvider` applies the theme from an effect, which runs *after* the
 * first paint — calling this from `main.tsx` first is what stops the shell
 * flashing the wrong theme on load.
 */
export function initTheme(): void {
  let stored: string | null = null
  try {
    stored = localStorage.getItem(STORAGE_KEYS.theme)
  } catch {
    // Private mode or a blocked store — fall through to the system theme.
  }
  const preference: ThemePreference =
    stored === 'light' || stored === 'dark' || stored === 'system' ? stored : 'system'
  applyTheme(resolveTheme(preference))
}

/** Subscribe to OS theme changes. Returns an unsubscribe function. */
export function watchSystemTheme(onChange: (name: ThemeName) => void): () => void {
  if (typeof window === 'undefined' || !window.matchMedia) return () => {}

  const media = window.matchMedia(DARK_QUERY)
  const handler = (event: MediaQueryListEvent) => onChange(event.matches ? 'dark' : 'light')
  media.addEventListener('change', handler)
  return () => media.removeEventListener('change', handler)
}
