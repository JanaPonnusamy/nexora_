// Purchase Manager (Procurement Sprint 2) types.

export interface Refresh {
  refresh_id: string
  cycle_id: string
  snapshot_name: string
  snapshot_status: string
  /** Read-only header fields (already returned by GET /vpl). */
  refresh_no?: number | null
  rolling_days?: number | null
  min_days?: number | null
  max_days?: number | null
  /** Products that need procurement in this Refresh (the VPL size). */
  generated_product_count?: number | null
  created_at?: string | null
  store_id?: string | null
}

/** A Procurement (Business) Cycle — Admin lifecycle screens. */
export interface Cycle {
  cycle_id: string
  tenant_id: string
  store_id: string | null
  name: string
  description: string | null
  status: string
  start_date: string | null
  end_date: string | null
  start_grn_number: string | null
  start_sale_bill_number: string | null
  end_grn_number: string | null
  end_sale_bill_number: string | null
  active_refresh_id: string | null
  created_at: string | null
  created_by: string | null
}

/** Result of closing a cycle. When pending items remain and the close was not
 *  forced, the API returns `pending_confirm` so the UI can prompt. */
export type CloseCycleResult =
  | { status: 'pending_confirm'; cycle_id: string; pending_count: number; message: string }
  | {
      status: 'closed'
      cycle: Cycle
      new_cycle: Cycle
      pending_cleared: number
      end_grn_number: string | null
      end_sale_bill_number: string | null
    }

/** Batched supplier recommendations for a working item (Product Grid icons). */
export interface SupplierRecommendation {
  order_item_id: string
  product_code: string | null
  suppliers: SupplierRow[]
}

/** A canonical mapping target for the supplier-stock Excel importer. */
export interface MappingTarget {
  value: string
  label: string
  mandatory: boolean
}

/** Preview of an uploaded supplier-stock Excel (headers + sample + suggested map). */
export interface SupplierStockPreview {
  headers: string[]
  sample: string[][]
  suggested: Record<string, string>
  targets: MappingTarget[]
}

export interface WorkspaceItem {
  order_item_id: string
  store_id: string | null
  product_id: string
  product_code: string | null
  product_name: string | null
  unit_description: string | null
  pack: string | null
  current_stock_qty: number | null
  mrp: number | null
  ptr_cost: number | null
  last_purchase_rate: number | null
  movement_class: string | null
  stock_status: string | null
  days_cover: number | null
  reason_code: string | null
  suggested_qty: number | null
  final_qty: number | null
  assigned_qty: number | null
  remaining_qty: number | null
  item_status: string
  supplier_code: string | null
  manual_override: boolean | null
  is_manual: boolean | null
  override_reason: string | null
  skip_reason: string | null
  /** Product Master classification (sync.Products.ProductType): 1=Pharma,
   *  0=Non-Pharma, 2=Others. Read-only; drives the Product Type filter. */
  product_type?: number | null
  /** Compact supplier offer/scheme (e.g. "10+1", "5% OFF") — read-only in the
   *  grid. Optional: only present when the workspace API supplies it. */
  offer?: string | null
}

/** Purchase Manager operating modes (Sprint: PM UI redesign). */
export type PurchaseMode = 'review' | 'supplier' | 'supplier-stock'

/** A product returned by the Manual Add Product search over sync.Products. */
export interface ManualProduct {
  product_code: string
  product_name: string | null
  unit: string | null
  current_stock: number | null
  mrp: number | null
}

/** One row of a supplier's live stock (supplier_stock ∩ SupplierProductMatch ∩
 *  current VPL), as returned by GET /refreshes/{id}/supplier-stock. */
export interface SupplierStockRow {
  supplier_code: string
  supplier_product_code: string | null
  supplier_product_name: string | null
  product_code: string | null
  product_name: string | null
  available_stock: number | null
  ptr: number | null
  mrp: number | null
  discount: number | null
  packing: string | null
  free: number | null
  minimum_qty: number | null
  scheme: string | null
  transaction_date: string | null
  suggested_qty: number | null
  final_qty: number | null
}

export interface WorkspacePage {
  items: WorkspaceItem[]
  total: number
  page: number
  page_size: number
}

/** Footer counts for the whole refresh, computed server-side. Purchase Value
 *  is intentionally not part of this — it stays client-computed (see
 *  workspace_repository.get_summary's docstring for why). */
export interface WorkspaceSummary {
  total: number
  pending_review: number
  assigned: number
  finalized: number
  skipped: number
}

export interface Assignment {
  assignment_id: string
  order_item_id: string
  supplier_code: string
  assigned_qty: number | null
  assignment_status: string
  remarks: string | null
  export_batch_number: string | null
  export_uid: string | null
  exported_at: string | null
}

export interface SupplierRow {
  supplier_code: string
  supplier_name: string | null
  purchase_frequency: number | null
  last_grn_date: string | null
  last_grn_no: string | null
  last_purchase_rate: number | null
  avg_lead_days: number | null
}

export interface SupplierQueue {
  order_item_id: string
  product_id: string
  product_code: string | null
  suppliers: SupplierRow[]
}

export interface ExportBatch {
  export_batch_number: string
  exported_at: string | null
  line_count: number
  supplier_count: number
  total_qty: number | null
}

export interface PendingItem {
  order_item_id: string
  product_id: string
  product_code: string | null
  product_name: string | null
  movement_class: string | null
  stock_status: string | null
  is_manual: boolean | null
  final_qty: number | null
  assigned_qty: number | null
  received_qty: number | null
  remaining_qty: number | null
  item_status: string
  pending_status: string | null
  supplier_code: string | null
}

export interface PendingPage {
  items: PendingItem[]
  total: number
  page: number
  page_size: number
}

export interface DecisionDetail {
  order_item_id: string
  product_code: string | null
  product_name: string | null
  item_status: string
  avg_daily_sales: number | null
  window_sales_qty: number | null
  max_day_sale_qty?: number | null
  current_stock_qty: number | null
  available_stock_qty?: number | null
  effective_available_qty: number | null
  pending_used_qty: number | null
  assigned_qty?: number | null
  days_cover: number | null
  target_days?: number | null
  target_stock_qty: number | null
  required_qty: number | null
  suggested_qty: number | null
  final_qty: number | null
  remaining_qty: number | null
  procurement_action?: string | null
  trigger_reason?: string | null
  reason_code: string | null
  reason_text: string | null
  business_rules_applied: string[]
}

export interface GrnResult {
  refresh_id: string
  last_grn_number: string
  assignments_matched: number
  items_completed: number
  items_partial: number
  items_pending: number
}

export interface WorkspaceFilters {
  search?: string
  item_status?: string
  movement_class?: string
  stock_status?: string
  sort_by?: string
  sort_dir?: string
  page?: number
  page_size?: number
}

/* ---- Supplier Order Optimization Engine --------------------------------- */

/** One suggested move of a product from its current supplier into a
 *  below-minimum supplier (Accept applies it via the assignment change path). */
export interface OptimizationMove {
  assignment_id: string
  order_item_id: string
  product_code: string | null
  product_name: string | null
  from_supplier: string
  to_supplier: string
  qty: number
  value: number
}

export type OptimizationStatus = 'ok' | 'ready' | 'short' | 'no_solution'

/** A supplier row in the optimization summary (§5/§7). */
export interface OptimizationSupplier {
  supplier_code: string
  supplier_name?: string | null
  min_value: number
  current_value: number
  gap: number
  projected_value: number
  current_products: number
  status: OptimizationStatus
  suggestions: OptimizationMove[]
  /** Full movable pool (below-minimum suppliers only) — powers Manual Move. */
  movable?: OptimizationMove[]
}

export interface OptimizationResult {
  refresh_id: string
  store_id: string | null
  price_tolerance: number
  use_live_stock: boolean
  below_minimum: number
  suppliers: OptimizationSupplier[]
}

export interface OptimizationMoveResult {
  moved: number
  skipped: number
  results: { assignment_id: string; status: string; reason?: string }[]
}

/** An audit row for a product moved between suppliers (§12). */
export interface OptimizationAuditRow {
  move_id: string
  order_item_id: string
  assignment_id: string
  product_code: string | null
  from_supplier: string | null
  to_supplier: string
  moved_qty: number | null
  moved_value: number | null
  reason: 'auto' | 'manual'
  moved_by: string | null
  moved_at: string | null
}
