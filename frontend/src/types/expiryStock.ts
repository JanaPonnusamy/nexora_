// Expiry Stock (Cutting Expiry) report types.

export interface ExpiryStockColumn {
  key: string
  label: string
  align: 'left' | 'right' | 'center'
  format: 'money' | 'int' | 'qty' | 'date' | 'mark' | null
  /** Optional columns default to hidden (added via the column settings). */
  optional?: boolean
}

export interface ExpiryStockResult {
  level: string
  columns: ExpiryStockColumn[]
  rows: Record<string, unknown>[]
  summary: Record<string, unknown> | null
}

export interface ExpiryStockSupplier {
  SupplierCode: string
  SupplierName: string
}
