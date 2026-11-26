import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';
import {
  normalizeThemePreference,
  resolveTheme,
  DEFAULT_THEME_PREFERENCE,
  themeById,
  variablesForTheme,
  nativeThemeSource,
} from './themeLogic.js';

const STORAGE_KEY = 'nextech.theme.preference';

const ThemeContext = createContext(null);

function readStoredPreference() {
  try {
    return normalizeThemePreference(window.localStorage.getItem(STORAGE_KEY));
  } catch {
    return DEFAULT_THEME_PREFERENCE;
  }
}

function prefersLight() {
  return window.matchMedia?.('(prefers-color-scheme: light)').matches ?? false;
}

function paint(preference) {
  const themeId = resolveTheme(preference, prefersLight());
  const theme = themeById(themeId);
  const root = document.documentElement;
  const vars = variablesForTheme(themeId);
  Object.entries(vars).forEach(([key, value]) => {
    root.style.setProperty(key, value);
  });
  root.setAttribute('data-theme', themeId);
  root.setAttribute('data-theme-preference', preference);
  root.setAttribute('data-bs-theme', theme.mode);
  root.style.colorScheme = theme.mode;
  return themeId;
}

export function ThemeProvider({ children }) {
  const [preference, setPreferenceState] = useState(readStoredPreference);
  const [themeId, setThemeId] = useState(() => resolveTheme(readStoredPreference(), prefersLight()));

  useEffect(() => {
    const resolved = paint(preference);
    setThemeId(resolved);
    try {
      window.localStorage.setItem(STORAGE_KEY, preference);
    } catch {
      // Best-effort persistence only.
    }
    const native = nativeThemeSource(preference);
    window.nextechMediq?.theme?.setPreference(native).catch(() => {});
  }, [preference]);

  useEffect(() => {
    if (preference !== 'system') return undefined;
    const media = window.matchMedia?.('(prefers-color-scheme: light)');
    if (!media) return undefined;
    const handler = () => setThemeId(paint('system'));
    media.addEventListener('change', handler);
    return () => media.removeEventListener('change', handler);
  }, [preference]);

  const value = useMemo(
    () => ({
      preference,
      themeId,
      effectiveTheme: themeById(themeId).mode,
      theme: themeById(themeId),
      setPreference: (next) => setPreferenceState(normalizeThemePreference(next)),
    }),
    [preference, themeId]
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used within a ThemeProvider');
  return ctx;
}
