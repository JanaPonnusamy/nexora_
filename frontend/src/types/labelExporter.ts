/* Types for the Label Exporter module. */

/* ---------- Product search ---------- */

export interface LabelSearchRow {
  product_code: string
  product_name: string
  unit_description: string | null
  box_number: string | null
  mrp: number
  total_stock: number
  sale_days: number | null
  purchase_days: number | null
  current_sublocation?: string | null
  sale_unit?: number | null
}

export interface LabelSearchResult {
  rows: LabelSearchRow[]
  unit_descriptions: string[]
  last_box_for_letter: string | null
}

/* ---------- Box search ---------- */

export interface LabelBoxRow {
  box_number: string
  product_count: number
  total_stock: number
  best_sale_days: number | null
  best_purchase_days: number | null
}

export interface BoxSearchResult {
  boxes: LabelBoxRow[]
}

/* ---------- Box products ---------- */

export interface LabelBoxProductRow {
  product_code: string
  product_name: string
  unit_description: string | null
  mrp: number
  total_stock: number
  sale_days: number | null
  purchase_days: number | null
}

export interface BoxProductResult {
  rows: LabelBoxProductRow[]
}

/* ---------- Batch detail ---------- */

export interface LabelBatchRow {
  product_code: string
  batch_code: string
  stock: number
  expiry_date: string | null
  mrp: number
  sale_days: number | null
  purchase_days: number | null
  is_expired: boolean
}

export interface ProductBatchResult {
  rows: LabelBatchRow[]
}

/* ---------- Letter-wise review ---------- */

export type IncludeLabel = 'Y' | 'N'
export type ProductKind = 'counter' | 'consumer'
export type SuggestionStatus = 'none' | 'pending' | 'approved' | 'rejected'

export interface LabelReviewRow {
  product_code: string
  product_name: string
  unit_description: string | null
  current_sublocation: string | null
  mrp: number
  total_stock: number
  include_label: IncludeLabel | null
  product_kind: ProductKind | null
  suggested_unit_description: string | null
  suggestion_status: SuggestionStatus
  final_unit_description: string | null
}

export interface LabelReviewListResult {
  rows: LabelReviewRow[]
}

export interface LabelReviewUpdateRequest {
  include_label?: IncludeLabel | null
  product_kind?: ProductKind | null
  suggested_unit_description?: string | null
}

export interface LabelSuggestionRow {
  tenant_id: string
  store_id: string
  product_code: string
  product_name: string
  current_unit_description: string | null
  suggested_unit_description: string | null
  suggested_by: string | null
  suggested_at: string | null
  suggestion_status: SuggestionStatus
}

export interface LabelSuggestionListResult {
  rows: LabelSuggestionRow[]
}
