/**
 * theme.ts — the single source of truth for every colour in the application.
 *
 * Nothing else should declare a colour literal. CSS reads these through the
 * `--nx-*` custom properties emitted by `applyTheme()`; TypeScript reads them
 * by importing the objects below.
 *
 * The bridge in `bootstrapBridge()` also feeds these values into Bootstrap's
 * own `--bs-*` variables, which is what lets existing pages pick up the
 * palette without being edited.
 */

/* ------------------------------------------------------------------ *
 * Raw ramp — the only place bare hex values are allowed to live.
 * Semantic tokens below reference these; components never do.
 * ------------------------------------------------------------------ */
export const palette = {
  white: '#ffffff',
  black: '#000000',

  // Cool slate neutral — biased slightly toward the accent hue so greys
  // read as chosen rather than inherited.
  slate25: '#f8fafc',
  slate50: '#f4f6fa',
  slate100: '#f1f4f9',
  slate150: '#e9eef5',
  slate200: '#e3e8f0',
  slate300: '#cbd5e1',
  slate400: '#94a3b8',
  slate500: '#64748b',
  slate600: '#475569',
  slate700: '#334155',
  slate800: '#1e293b',
  slate850: '#17202d',
  slate900: '#111823',
  slate950: '#0a0f17',

  blue300: '#93b8fd',
  blue400: '#6d9fff',
  blue500: '#4f8df7',
  blue600: '#2563eb',
  blue700: '#1d4ed8',
  blue900: '#15243d',
  blue50: '#e8f0fe',

  green400: '#4ade94',
  green500: '#10b981',
  green600: '#059669',
  green700: '#047857',
  green50: '#dcfce7',
  green950: '#0c2a22',

  amber300: '#fbbf24',
  amber500: '#f59e0b',
  amber600: '#d97706',
  amber700: '#b45309',
  amber50: '#fef3c7',
  amber950: '#2e2210',

  red300: '#fca5a5',
  red500: '#ef4444',
  red600: '#dc2626',
  red700: '#b91c1c',
  red50: '#fee2e2',
  red950: '#331618',

  cyan300: '#67e8f9',
  cyan500: '#22b8cf',
  cyan600: '#0891b2',
  cyan700: '#0e7490',
  cyan50: '#cffafe',
  cyan950: '#0c2830',
} as const

/* ------------------------------------------------------------------ *
 * Semantic tokens — what components actually consume.
 * ------------------------------------------------------------------ */
export interface ThemeTokens {
  /** App background behind all panels. */
  canvas: string
  /** Cards, header, sidebar — the primary raised plane. */
  surface: string
  /** Popovers, flyouts, dropdowns — floats above `surface`. */
  surfaceRaised: string
  /** Inputs, wells, table stripes — recedes below `surface`. */
  surfaceSunk: string
  /** Row and control hover. */
  surfaceHover: string

  /** Hairline dividers and card borders. */
  rule: string
  /** Emphasised borders — focused inputs, active outlines. */
  ruleStrong: string

  /** Primary body and heading text. */
  text: string
  /** Secondary text — descriptions, table cells. */
  textSoft: string
  /** Tertiary text — labels, captions, placeholders. */
  textMuted: string
  /** Text placed on a filled accent/semantic ground. */
  textOn: string

  accent: string
  accentHover: string
  /** Tinted accent ground — active nav, selected rows, badges. */
  accentSunk: string
  /** Accent-coloured text sitting on `accentSunk`. */
  accentInk: string

  success: string
  successSunk: string
  successInk: string

  warning: string
  warningSunk: string
  warningInk: string

  danger: string
  dangerSunk: string
  dangerInk: string

  info: string
  infoSunk: string
  infoInk: string

  /** Keyboard focus ring. */
  focus: string
  /** Scrim behind modals and the mobile nav drawer. */
  scrim: string

  shadowSm: string
  shadowMd: string
  shadowLg: string
}

export const lightTheme: ThemeTokens = {
  canvas: palette.slate50,
  surface: palette.white,
  surfaceRaised: palette.white,
  surfaceSunk: palette.slate100,
  surfaceHover: palette.slate150,

  rule: palette.slate200,
  ruleStrong: palette.slate300,

  text: '#0f172a',
  textSoft: palette.slate600,
  textMuted: palette.slate500,
  textOn: palette.white,

  accent: palette.blue600,
  accentHover: palette.blue700,
  accentSunk: palette.blue50,
  accentInk: palette.blue700,

  success: palette.green600,
  successSunk: palette.green50,
  successInk: palette.green700,

  warning: palette.amber600,
  warningSunk: palette.amber50,
  warningInk: palette.amber700,

  danger: palette.red600,
  dangerSunk: palette.red50,
  dangerInk: palette.red700,

  info: palette.cyan600,
  infoSunk: palette.cyan50,
  infoInk: palette.cyan700,

  focus: 'rgba(37, 99, 235, 0.35)',
  scrim: 'rgba(15, 23, 42, 0.45)',

  shadowSm: '0 1px 2px rgba(15, 23, 42, 0.06)',
  shadowMd: '0 2px 4px rgba(15, 23, 42, 0.06), 0 8px 20px -12px rgba(15, 23, 42, 0.22)',
  shadowLg: '0 4px 8px rgba(15, 23, 42, 0.07), 0 20px 40px -20px rgba(15, 23, 42, 0.28)',
}

export const darkTheme: ThemeTokens = {
  canvas: palette.slate950,
  surface: palette.slate900,
  surfaceRaised: palette.slate850,
  surfaceSunk: '#0d141e',
  surfaceHover: '#1a2331',

  rule: '#212c3a',
  ruleStrong: '#32404f',

  text: '#e7edf5',
  textSoft: '#b6c2d2',
  textMuted: '#8494a8',
  textOn: palette.white,

  accent: palette.blue500,
  accentHover: palette.blue400,
  accentSunk: palette.blue900,
  accentInk: palette.blue300,

  success: palette.green500,
  successSunk: palette.green950,
  successInk: palette.green400,

  warning: palette.amber500,
  warningSunk: palette.amber950,
  warningInk: palette.amber300,

  danger: palette.red500,
  dangerSunk: palette.red950,
  dangerInk: palette.red300,

  info: palette.cyan500,
  infoSunk: palette.cyan950,
  infoInk: palette.cyan300,

  focus: 'rgba(109, 159, 255, 0.45)',
  scrim: 'rgba(2, 6, 12, 0.66)',

  shadowSm: '0 1px 2px rgba(0, 0, 0, 0.4)',
  shadowMd: '0 2px 4px rgba(0, 0, 0, 0.4), 0 8px 20px -12px rgba(0, 0, 0, 0.7)',
  shadowLg: '0 4px 8px rgba(0, 0, 0, 0.45), 0 20px 40px -20px rgba(0, 0, 0, 0.8)',
}

export const themes = { light: lightTheme, dark: darkTheme } as const
export type ThemeName = keyof typeof themes

/* ------------------------------------------------------------------ *
 * Shell geometry — sizes the layout depends on, kept beside the colours
 * so the shell has one import rather than several.
 * ------------------------------------------------------------------ */
export const layout = {
  headerHeight: '52px',
  statusbarHeight: '30px',
  /** Only one sidebar width exists — there is no collapsed variant. */
  sidebarWidth: '204px',
  flyoutWidth: '232px',
  gutter: '1.25rem',
  radiusSm: '6px',
  radiusMd: '8px',
  radiusLg: '12px',
} as const

export const zLayers = {
  header: 100,
  sidebar: 90,
  navFlyout: 1065,
  drawerScrim: 1020,
  drawer: 1030,
  dropdown: 1060,
  modal: 1080,
} as const

/* ------------------------------------------------------------------ *
 * Emitters — turn the objects above into CSS custom properties.
 * ------------------------------------------------------------------ */

/** camelCase -> kebab-case (`surfaceRaised` -> `surface-raised`). */
function kebab(key: string): string {
  return key.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`)
}

/** Expand `#rrggbb` to an `"r, g, b"` triplet for `rgb(var(--x) / <alpha>)`. */
function rgbTriplet(hex: string): string | null {
  const match = /^#([0-9a-f]{6})$/i.exec(hex.trim())
  if (!match) return null
  const int = parseInt(match[1], 16)
  return `${(int >> 16) & 255}, ${(int >> 8) & 255}, ${int & 255}`
}

/** `--nx-*` custom properties for one theme. */
export function themeVariables(tokens: ThemeTokens): Record<string, string> {
  const vars: Record<string, string> = {}
  for (const [key, value] of Object.entries(tokens)) {
    vars[`--nx-${kebab(key)}`] = value
    const triplet = rgbTriplet(value)
    if (triplet) vars[`--nx-${kebab(key)}-rgb`] = triplet
  }
  return vars
}

/** Static `--nx-*` properties for shell geometry (theme-independent). */
export function layoutVariables(): Record<string, string> {
  const vars: Record<string, string> = {}
  for (const [key, value] of Object.entries(layout)) {
    vars[`--nx-${kebab(key)}`] = value
  }
  for (const [key, value] of Object.entries(zLayers)) {
    vars[`--nx-z-${kebab(key)}`] = String(value)
  }
  return vars
}

/**
 * Bootstrap bridge — the reason 43 existing pages restyle for free.
 *
 * Bootstrap components read `--bs-*` at the root, so pointing those at our
 * tokens re-skins every card, table, form and button already in the app
 * without touching their markup.
 */
export function bootstrapBridge(tokens: ThemeTokens): Record<string, string> {
  const bodyRgb = rgbTriplet(tokens.canvas)
  const textRgb = rgbTriplet(tokens.text)
  const accentRgb = rgbTriplet(tokens.accent)

  const vars: Record<string, string> = {
    '--bs-body-bg': tokens.canvas,
    '--bs-body-color': tokens.text,
    '--bs-emphasis-color': tokens.text,
    '--bs-secondary-color': tokens.textMuted,
    '--bs-secondary-bg': tokens.surfaceSunk,
    '--bs-tertiary-bg': tokens.surfaceHover,
    '--bs-tertiary-color': tokens.textMuted,
    '--bs-border-color': tokens.rule,
    '--bs-border-color-translucent': tokens.rule,

    '--bs-primary': tokens.accent,
    '--bs-link-color': tokens.accent,
    '--bs-link-hover-color': tokens.accentHover,

    '--bs-success': tokens.success,
    '--bs-warning': tokens.warning,
    '--bs-danger': tokens.danger,
    '--bs-info': tokens.info,

    '--bs-success-bg-subtle': tokens.successSunk,
    '--bs-warning-bg-subtle': tokens.warningSunk,
    '--bs-danger-bg-subtle': tokens.dangerSunk,
    '--bs-info-bg-subtle': tokens.infoSunk,
    '--bs-primary-bg-subtle': tokens.accentSunk,

    '--bs-success-text-emphasis': tokens.successInk,
    '--bs-warning-text-emphasis': tokens.warningInk,
    '--bs-danger-text-emphasis': tokens.dangerInk,
    '--bs-info-text-emphasis': tokens.infoInk,
    '--bs-primary-text-emphasis': tokens.accentInk,

    '--bs-success-border-subtle': tokens.successSunk,
    '--bs-warning-border-subtle': tokens.warningSunk,
    '--bs-danger-border-subtle': tokens.dangerSunk,
    '--bs-info-border-subtle': tokens.infoSunk,
    '--bs-primary-border-subtle': tokens.accentSunk,

    // Surfaces Bootstrap derives from the body background. Our canvas is
    // intentionally darker/greyer than card surfaces, so these are pinned
    // to `surface` rather than inheriting the canvas.
    '--bs-card-bg': tokens.surface,
    '--bs-card-border-color': tokens.rule,
    '--bs-modal-bg': tokens.surfaceRaised,
    '--bs-dropdown-bg': tokens.surfaceRaised,
    '--bs-dropdown-border-color': tokens.rule,
    '--bs-dropdown-link-color': tokens.textSoft,
    '--bs-dropdown-link-hover-bg': tokens.surfaceHover,
    '--bs-dropdown-link-hover-color': tokens.text,

    '--bs-form-control-bg': tokens.surface,
    '--bs-table-bg': tokens.surface,
    '--bs-table-border-color': tokens.rule,
    '--bs-table-striped-bg': tokens.surfaceSunk,
    '--bs-table-hover-bg': tokens.surfaceHover,
  }

  if (bodyRgb) vars['--bs-body-bg-rgb'] = bodyRgb
  if (textRgb) {
    vars['--bs-body-color-rgb'] = textRgb
    vars['--bs-emphasis-color-rgb'] = textRgb
  }
  if (accentRgb) vars['--bs-primary-rgb'] = accentRgb

  return vars
}

/** Everything that should be set on `:root` for a given theme. */
export function rootVariables(name: ThemeName): Record<string, string> {
  const tokens = themes[name]
  return {
    ...layoutVariables(),
    ...themeVariables(tokens),
    ...bootstrapBridge(tokens),
  }
}
