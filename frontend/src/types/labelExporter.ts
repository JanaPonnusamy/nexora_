/* Types for the Label Exporter module. */

/* ---------- Product search / review grid ---------- */

export type IncludeLabel = 'Y' | 'N'
export type UnitDescriptionMode = 'contains' | 'exact' | 'null'
export type StockFilter = 'all' | 'in_stock' | 'zero_recent_sale' | 'zero_stale'
/** '' = any, 'unreviewed' = include_label IS NULL, 'Y'/'N' = that decision. */
export type ReviewStatusFilter = '' | 'unreviewed' | 'Y' | 'N'

export interface LabelSearchRow {
  product_code: string
  product_name: string
  /** Master unit from sync.Products (the historical / OLD unit before any correction). */
  unit_description: string | null
  mrp: number
  total_stock: number
  sale_days: number | null
  purchase_days: number | null
  /** Master shelf SubLocation from sync.Products (the OLD location). */
  current_sublocation?: string | null
  sale_unit?: number | null
  include_label?: IncludeLabel | null
  remarks?: string | null
  /** Reviewer's corrected unit (label_review.unit_description); '' when uncorrected. */
  corrected_unit?: string | null
  /** Master unit captured at correction time (label_review.old_unit_description); '' when uncorrected. */
  old_unit_description?: string | null
  /** Box assigned by the assignment engine (label_review.assigned_sublocation); '' when unassigned. */
  assigned_sublocation?: string | null
  /** Location captured when the assignment was made (label_review.old_sublocation). */
  old_sublocation?: string | null
  assignment_type?: string | null
  label_required?: boolean
  batch_stock?: number
}

export interface LabelSearchResult {
  rows: LabelSearchRow[]
  unit_descriptions: string[]
  sublocations: string[]
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

/* ---------- Review (Y/N + remarks) ---------- */

export interface LabelReviewUpdateRequest {
  include_label?: IncludeLabel | null
  remarks?: string | null
}

/* ---------- Sublocation assignment (super admin, manual single) ---------- */

export interface LabelSublocationAssignRequest {
  sublocation: string
}

/* ---------- Unit correction ---------- */

export interface LabelUnitCorrectionRequest {
  unit_description: string
  current_unit?: string
}

/* ---------- Product trend / intelligence panels ---------- */

export interface LabelTrendRow {
  month: string
  sale_qty: number
  purchase_qty: number
  stock_in_hand: number
}

export interface LabelTrendResult {
  rows: LabelTrendRow[]
}

export interface LabelPurchaseRow {
  stock: number
  free_qty: number
  discount_pct: number
  item_cost: number
  ptr: number
  mrp: number
  grn_date: string | null
  supplier_name: string | null
}

export interface LabelPurchaseResult {
  rows: LabelPurchaseRow[]
}

export interface LabelSaleRow {
  qty: number
  bill_time: string | null
  salesman: string | null
  customer: string | null
  discount_pct: number
  mrp: number
}

export interface LabelSaleResult {
  rows: LabelSaleRow[]
}

/* ---------- Location assignment (preview + commit) ---------- */

export type AssignmentMode = 'continue' | 'new_label' | 'single'
export type AssignmentType = 'standard_box' | 'single_product_box'

export interface LabelAssignRequest {
  unit: string
  mode: AssignmentMode
  assignment_type: AssignmentType
  letter: string
  product_codes: string[]
  start_number?: number
}

export interface LabelAssignBox {
  box: string
  existing: number
  added: number
  total: number
  capacity: number | null
}

export interface LabelAssignEntry {
  product_code: string
  product_name: string
  box: string
  slot: number
}

export interface LabelAssignResult {
  unit: string
  mode: string
  assignment_type: string
  assignments: LabelAssignEntry[]
  boxes: LabelAssignBox[]
  assigned_count: number
  committed: boolean
}

/* ---------- Label queue ---------- */

export interface LabelQueueRow {
  product_code: string
  product_name: string
  location: string | null
  unit_description: string | null
  mrp: number
  sale_unit: number | null
  assignment_type: string | null
  assigned_at: string | null
  label_created_at: string | null
}

export interface LabelQueueResult {
  rows: LabelQueueRow[]
}
