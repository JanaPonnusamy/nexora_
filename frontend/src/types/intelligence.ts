import type { PurchaseRow, SalesRow } from './stock'

/** One dynamically-discovered store column in the grid header. */
export interface PiStoreColumn {
  store_id: string
  store_code: string | null
  store_name: string | null
  is_warehouse: boolean
  refresh_id: string | null
  vpl_product_count: number | null
  vpl_generated_on: string | null
}

/** One product × store cell (absent = blank cell: the store does not have it). */
export interface PiStoreCell {
  store_id: string
  product_code: string | null
  suggested_qty: number | null
  stock_qty: number | null
  avg_sale: number | null
  sales_qty: number | null
  purchase_qty: number | null
  days_cover: number | null
  /** 1 = the store's own VPL asked for this (real demand); 0 = stock only. */
  in_vpl: number | null
  last_sale_date: string | null
  last_purchase_date: string | null
  non_moving_days: number | null
  match_method: string | null
}

/** One CANONICAL supplier product — the grid row. Quantities are network-wide:
 *  consolidated_suggest_qty is the sum of EVERY store's own suggested qty, and
 *  consolidated_purchase_qty is what the warehouse must buy for the network. */
export interface PiRow {
  cache_id: string
  common_product_id: string
  product_code: string | null
  product_name: string | null
  manufacturer_id: string | null
  supplier_code: string | null
  supplier_product_code: string | null
  supplier_product_name: string | null
  consolidated_suggest_qty: number
  consolidated_purchase_qty: number
  consolidated_stock_qty: number
  transfer_qty: number
  mapped_store_count: number
  warehouse_stock_qty: number | null
  /** null = the warehouse does not stock this product at all. */
  warehouse_product_code: string | null
  warehouse_suggest_qty: number | null
  total_sales_qty: number | null
  total_purchase_qty: number | null
  priority: string | null
  priority_rank: number | null
  stockout_store_count: number | null
  confidence: number | null
  match_method: string | null
  mrp: number | null
  ptr_cost: number | null
  last_purchase_rate: number | null
  margin: number | null
  offer_text: string | null
  /** Per-store cells keyed by store_id. Missing key = blank cell. */
  stores: Record<string, PiStoreCell>
}

export interface PiBuild {
  build_id: string
  tenant_id: string
  refresh_id: string
  warehouse_store_id: string | null
  anchor_store_id: string | null
  product_count: number
  store_count: number
  rolling_days: number | null
  total_need_qty: number | null
  total_suggest_qty: number
  total_purchase_qty: number
  total_transfer_qty: number
  total_stock_qty: number
  status: string
  generated_on: string
}

export interface PiSummary {
  build_id: string
  warehouse_store_id: string | null
  generated_on: string
  total_products: number
  store_count: number
  need_quantity: number
  purchase_quantity: number
  transfer_quantity: number
  stock_quantity: number
}

export interface PiGrid {
  build: PiBuild
  stores: PiStoreColumn[]
  rows: PiRow[]
  summary: PiSummary
}

export type PiProduct = Omit<PiRow, 'stores'> & {
  build_id: string
  tenant_id: string
  refresh_id: string
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
  sales_qty: number | null
  purchase_qty: number | null
  days_cover: number | null
  in_vpl: number | null
  is_warehouse: number | null
  last_sale_date: string | null
  last_purchase_date: string | null
  non_moving_days: number | null
}

export interface PiDetail {
  product: PiProduct
  stores: PiDetailStore[]
}

/** One month of one store's transactions (a bar in that store's chart). */
export interface PiChartPoint {
  period: string
  sales_qty: number
  purchase_qty: number
}

/** One store's chart. The store is resolved BY PRODUCT NAME, independently of
 *  every other store — the mapping is not used here. */
export interface PiChartSeries {
  store_id: string
  store_code: string | null
  store_name: string | null
  is_warehouse: boolean
  product_code: string | null
  product_name: string | null
  found: boolean
  points: PiChartPoint[]
}

export interface PiCharts {
  cache_id: string
  product_name: string | null
  months: number
  /** Shared month axis — every series has one point per axis entry. */
  axis: string[]
  series: PiChartSeries[]
}

/** One store's transaction history (loaded only for the store the user opens). */
export interface PiHistory {
  cache_id: string
  store_id: string
  mapped: boolean
  product_code?: string | null
  product_name?: string | null
  stock_qty?: number | null
  suggested_qty?: number | null
  sales_qty?: number | null
  purchase_qty?: number | null
  avg_sale?: number | null
  in_vpl?: number | null
  last_sale_date?: string | null
  last_purchase_date?: string | null
  non_moving_days?: number | null
  sales_history: SalesRow[]
  purchase_history: PurchaseRow[]
  monthly_sales: { period: string; qty: number }[]
}

export interface PiBuildResult {
  build_id: string
  warehouse_store_id: string
  product_count: number
  store_count: number
  stores: { store_id: string; is_warehouse: boolean; vpl_product_count: number }[]
  total_need_qty: number
  total_purchase_qty: number
  total_transfer_qty: number
  total_stock_qty: number
}
