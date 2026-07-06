// Module-local formatters (kept isolated from shared utils on purpose).

export function num(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '0'
  return value.toLocaleString('en-IN', { maximumFractionDigits: 0 })
}

export function money(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—'
  return `₹${value.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export function date(value: string | null | undefined): string {
  if (!value) return '—'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: '2-digit' })
}

export type StockState = 'in' | 'out'

/** Binary indicator: in stock (green) vs out of stock (red). */
export function stockState(stock: number | null | undefined): StockState {
  return (stock ?? 0) > 0 ? 'in' : 'out'
}

export const STOCK_LEGEND: { state: StockState; label: string }[] = [
  { state: 'in', label: 'In Stock' },
  { state: 'out', label: 'Out of Stock' },
]

/* Per-store accent colours so each branch card is visually distinct. */
const STORE_COLORS = [
  { accent: '#4f46e5', soft: '#eef2ff' },
  { accent: '#0d9488', soft: '#d8f3ee' },
  { accent: '#d97706', soft: '#fef3c7' },
  { accent: '#7c3aed', soft: '#ede9fe' },
  { accent: '#0284c7', soft: '#e0f2fe' },
  { accent: '#15a34a', soft: '#dcfce7' },
  { accent: '#db2777', soft: '#fce7f3' },
  { accent: '#ca8a04', soft: '#fef9c3' },
]

export function storeColor(key: string): { accent: string; soft: string } {
  let hash = 0
  for (let i = 0; i < key.length; i++) hash = (hash * 31 + key.charCodeAt(i)) >>> 0
  return STORE_COLORS[hash % STORE_COLORS.length]
}
