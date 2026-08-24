export const THEME_PREFERENCES = ['light', 'dark'];

export function normalizeThemePreference(value) {
  return THEME_PREFERENCES.includes(value) ? value : 'light';
}

export function resolveTheme(preference) {
  return normalizeThemePreference(preference);
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
