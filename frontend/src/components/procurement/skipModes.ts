// Skip planning-modes. A skipped row's `skip_reason` stores one of these codes
// (no schema change — the column already holds free text) and the grid renders
// the label as the row's Planning State.
export const SKIP_MODES = [
  { code: 'current_refresh', label: 'Current Refresh' },
  { code: 'until_next_sales', label: 'Until Next Sales' },
  { code: 'until_next_demand', label: 'Until Next Demand' },
] as const

export type SkipModeCode = (typeof SKIP_MODES)[number]['code']

export const DEFAULT_SKIP_MODE: SkipModeCode = 'current_refresh'

/** Human label for a stored skip_reason; falls back to a generic "Skipped". */
export function skipModeLabel(code: string | null | undefined): string {
  return SKIP_MODES.find((m) => m.code === code)?.label ?? 'Skipped'
}
