// Expiry Report (supplier-expiry drill-down) types.

export interface ExpiryColumn {
  key: string
  label: string
  align: 'left' | 'right' | 'center'
  format: 'money' | 'int' | 'date' | null
}

export interface ExpiryResult {
  level: string
  columns: ExpiryColumn[]
  rows: Record<string, unknown>[]
  summary: Record<string, unknown> | null
}
