export const THEME_PREFERENCES = ['dark', 'light', 'system'];

export function normalizeThemePreference(value) {
  return THEME_PREFERENCES.includes(value) ? value : 'dark';
}

export function resolveTheme(preference, prefersDark) {
  const normalized = normalizeThemePreference(preference);
  if (normalized !== 'system') return normalized;
  if (typeof prefersDark === 'boolean') return prefersDark ? 'dark' : 'light';
  if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  return 'dark';
}

export function applyTheme(preference) {
  const theme = resolveTheme(preference);
  const root = document.documentElement;
  root.dataset.theme = theme;
  root.dataset.themePreference = normalizeThemePreference(preference);
  root.style.colorScheme = theme;
  window.nexoraDesktop?.setTheme?.(normalizeThemePreference(preference), theme);
  return theme;
}
