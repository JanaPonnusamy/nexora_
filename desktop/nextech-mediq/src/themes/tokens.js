// Centralized NexTech MediQ Workspace design tokens. Per Phase 2/3 directive:
// "Do not scatter hardcoded colors throughout components." Every component
// reads colors from CSS variables defined here (applied in tokens.css),
// never from an inline hex literal.

export const BRAND = {
  name: 'NexTech MediQ Workspace',
  tagline: 'Intelligent Pharmaceutical Workspace',
};

export const PALETTE = {
  primaryNavy: '#10243A',
  deepNavy: '#0B1728',
  teal: '#12B8A6',
  brightTeal: '#20D6C0',

  lightBackground: '#F4F7FA',
  darkBackground: '#0B1220',
  darkPanel: '#172337',
  darkElevated: '#203149',
  darkBorder: '#34465D',

  primaryText: '#F1F5F9',
  secondaryText: '#B8C5D6',

  success: '#22C55E',
  warning: '#F59E0B',
  error: '#EF4444',
};

export const THEME_PREFERENCES = Object.freeze(['dark', 'light', 'system']);
export const DEFAULT_THEME_PREFERENCE = 'dark';
