export interface StockCheckRow {
  product_code: string | null
  sublocation: string | null
  product_name: string | null
  total_stock: number
  batch_stock: number
  expiry_date: string | null
  mrp: number
  sale_unit: string | null
  batch_code: string | null
  purchase_days: number | null
  sale_days: number | null
}

export interface StockCheckResult {
  rows: StockCheckRow[]
}
