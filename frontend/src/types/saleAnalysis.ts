// Sale Analysis (grouped product-trend) types.
import type { ExpiryColumn } from './expiryReport'

export type SaleWindow = 'month' | 'last30' | 'range'

export interface SaleProductOption {
  product_code: string
  product_name: string | null
  supplier_code: string | null
  supplier_name: string | null
  current_stock: number | null
  mrp: number | null
}

export interface SaleSupplierOption {
  supplier_code: string
  supplier_name: string | null
}

export interface SaleGroupSummary {
  group_id: string
  group_name: string
  item_count: number
  updated_at: string | null
}

export interface SaleGroupDetail extends SaleGroupSummary {
  product_names: string[]
}

export interface SaleReportGroup {
  group_id: string | null
  group_name: string
  summary: Record<string, unknown>
  rows: Record<string, unknown>[]
}

export interface SaleAnalysisResult {
  window_label: string
  from_date: string
  to_date: string
  window_days: number
  target_days: number
  columns: ExpiryColumn[]
  groups: SaleReportGroup[]
  grand_summary: Record<string, unknown> | null
}
