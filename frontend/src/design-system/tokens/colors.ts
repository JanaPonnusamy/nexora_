/**
 * Colours live in `theme.ts`. This module stays as the convenience surface
 * for TypeScript consumers and re-exports from there — it deliberately holds
 * no literals of its own, so there is exactly one place a colour is defined.
 */
export { palette, lightTheme, darkTheme, themes } from './theme'
export type { ThemeTokens, ThemeName } from './theme'

/**
 * Semantic colours as CSS variable references, for inline styles and for
 * anywhere a value has to be handed to a non-CSS consumer (canvas, SVG
 * gradients, chart libraries).
 */
export const semanticColors = {
  canvas: 'var(--nx-canvas)',
  surface: 'var(--nx-surface)',
  surfaceRaised: 'var(--nx-surface-raised)',
  surfaceSunk: 'var(--nx-surface-sunk)',
  surfaceHover: 'var(--nx-surface-hover)',
  rule: 'var(--nx-rule)',
  ruleStrong: 'var(--nx-rule-strong)',
  text: 'var(--nx-text)',
  textSoft: 'var(--nx-text-soft)',
  textMuted: 'var(--nx-text-muted)',
  textOn: 'var(--nx-text-on)',
  accent: 'var(--nx-accent)',
  accentSunk: 'var(--nx-accent-sunk)',
  accentInk: 'var(--nx-accent-ink)',
  success: 'var(--nx-success)',
  warning: 'var(--nx-warning)',
  danger: 'var(--nx-danger)',
  info: 'var(--nx-info)',
  focus: 'var(--nx-focus)',
} as const
