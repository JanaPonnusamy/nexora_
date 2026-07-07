import type { PurchaseRow, SalesRow } from './stock'

/** One dynamically-discovered store column in the grid header. */
export interface PiStoreColumn {
  store_id: string
  store_code: string | null
  store_name: string | null
  product_count: number
}

/** One product × store cell (absent = blank cell: product not mapped there). */
export interface PiStoreCell {
  store_id: string
  product_code: string | null
  suggested_qty: number | null
  stock_qty: number | null
  avg_sale: number | null
  last_sale_date: string | null
  last_purchase_date: string | null
  non_moving_days: number | null
  match_method: string | null
}

/** One consolidated grid row (a product across all active stores). */
export interface PiRow {
  cache_id: string
  common_product_id: string
  product_code: string | null
  product_name: string | null
  manufacturer_id: string | null
  consolidated_suggest_qty: number
  consolidated_purchase_qty: number
  consolidated_stock_qty: number
  transfer_qty: number
  mapped_store_count: number
  mrp: number | null
  ptr_cost: number | null
  last_purchase_rate: number | null
  margin: number | null
  offer_text: string | null
  /** Per-store cells keyed by store_id. Missing key = blank (unmapped) cell. */
  stores: Record<string, PiStoreCell>
}

export interface PiBuild {
  build_id: string
  tenant_id: string
  refresh_id: string
  anchor_store_id: string | null
  product_count: number
  store_count: number
  rolling_days: number | null
  total_suggest_qty: number
  total_purchase_qty: number
  total_transfer_qty: number
  total_stock_qty: number
  status: string
  generated_on: string
}

export interface PiSummary {
  total_products: number
  purchase_quantity: number
  transfer_quantity: number
  stock_quantity: number
  suggest_quantity: number
}

export interface PiGrid {
  build: PiBuild
  stores: PiStoreColumn[]
  rows: PiRow[]
  summary: PiSummary
}

export interface PiProduct {
  cache_id: string
  build_id: string
  tenant_id: string
  refresh_id: string
  common_product_id: string
  product_code: string | null
  product_name: string | null
  manufacturer_id: string | null
  consolidated_suggest_qty: number
  consolidated_purchase_qty: number
  consolidated_stock_qty: number
  transfer_qty: number
  mapped_store_count: number
  mrp: number | null
  ptr_cost: number | null
  last_purchase_rate: number | null
  margin: number | null
  offer_text: string | null
}

export interface PiDetailStore {
  cache_store_id: string
  store_id: string
  store_code: string | null
  store_name: string | null
  product_id: string | null
  product_code: string | null
  product_name: string | null
  match_method: string | null
  stock_qty: number | null
  suggested_qty: number | null
  avg_sale: number | null
  last_sale_date: string | null
  last_purchase_date: string | null
  non_moving_days: number | null
}

export interface PiDetail {
  product: PiProduct
  stores: PiDetailStore[]
}

export interface PiHover {
  cache_id: string
  store_id: string
  mapped: boolean
  product_code?: string | null
  product_name?: string | null
  last_sale_date: string | null
  last_purchase_date: string | null
  non_moving_days: number | null
  sales_history: SalesRow[]
  purchase_history: PurchaseRow[]
}

export interface PiBuildResult {
  build_id: string
  refresh_id: string
  anchor_store_id: string | null
  product_count: number
  store_count: number
  total_suggest_qty: number
  total_purchase_qty: number
  total_transfer_qty: number
  total_stock_qty: number
}
