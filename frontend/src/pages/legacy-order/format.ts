/** Shared formatters for the Legacy Order pages. */

export function fmtDate(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleDateString()
}

/**
 * Quantity / stock formatter — full number with thousand separators and NO
 * abbreviation (req: show 1,300 / 10,500, never 1.3k / 10.5k). Non-numeric or
 * null values fall back to an em dash. Fractions are preserved (up to 2 dp) but
 * whole numbers stay whole so stock counts don't grow spurious decimals.
 */
export function fmtQty(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  const n = Number(value)
  if (!Number.isFinite(n)) return '—'
  return n.toLocaleString(undefined, { maximumFractionDigits: 2 })
}

/** Money formatter — always 2 dp with grouping; em dash for null/NaN. */
export function fmtMoney(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  const n = Number(value)
  if (!Number.isFinite(n)) return '—'
  return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
