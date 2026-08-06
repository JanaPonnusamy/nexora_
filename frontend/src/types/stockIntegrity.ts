export interface StockIntegrityRow {
  store_code: string | null
  store_name: string | null
  store_id: string | null
  product_code: string | null
  product_name: string | null
  store_batch_total: number
  nexora_total_stock: number
  difference: number
}

export interface StockIntegrityResult {
  rows: StockIntegrityRow[]
  mismatch_count: number
}

export interface StockIntegrityRepairResult {
  repaired: number
  remaining_mismatches: number
}
