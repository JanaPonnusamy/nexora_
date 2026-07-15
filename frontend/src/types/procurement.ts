// Purchase Manager (Procurement Sprint 2) types.

/** Shelf Sorting split files as a base64 manifest — for writing each file into
 *  a chosen output folder (desktop app, supports UNC/network paths). */
export interface ShelfSortManifest {
  files: { name: string; content_b64: string }[]
  total_products: number
  file_count: number
}

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

/** One product's diff between two refreshes of the same cycle. */
export type CompareChange = 'Added' | 'Removed' | 'Increased' | 'Decreased' | 'NoChange'
export interface CompareItem {
  product_id: string | null
  product_code: string | null
  product_name: string | null
  source_qty: number | null
  target_qty: number | null
  qty_difference: number | null
  change_type: CompareChange
}
export interface CompareResult {
  source_vpl_id: string
  target_vpl_id: string
  cycle_id: string
  items: CompareItem[]
  total: number
  page: number
  page_size: number
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

/** What POST /cycles/{id}/refreshes actually returns — the Decision Engine +
 *  VPL + working-item generation counts, exactly as the orchestration service
 *  already reports them. Note there is deliberately no supplier / deferred /
 *  skipped count here: a freshly generated Refresh has no reviewed items yet. */
export interface RefreshRunResult {
  refresh_id: string
  cycle_id: string
  status: string
  previous_refresh_id: string | null
  /** Products that need procurement — the VPL size. */
  generated_product_count: number
  included_count: number
  excluded_count: number
  /** Working order items generated from the VPL (suggested_qty > 0). */
  working_item_count: number
  /** Pending items carried over from the previous Refresh. */
  carried_forward_count: number
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
  deferred: number
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
  /** Carried on the assignment row itself (not just the workspace item) — a
   *  fallback display field so a Supplier Queue line is never dropped just
   *  because its order item isn't in the currently-loaded workspace page. */
  product_code: string | null
  /** This exact supplier's real scheme/free/discount for this exact product
   *  (procurement.supplier_stock, when a Live Stock import has mapped it) —
   *  a fresher manual feed, so it wins over pt_offer below when present.
   *  `discount` is a VARCHAR column that holds messy free-text in practice
   *  (not a clean percentage) — treat it as untrusted/best-effort. */
  offer_scheme?: number | null
  offer_free?: number | null
  offer_discount?: string | null
  /** Real purchase history from sync.PurchaseTrans — this row's own
   *  (product, supplier) pair's most recent purchase. */
  pt_ptr?: number | null
  pt_cost?: number | null
  pt_mrp?: number | null
  pt_last_purchase_date?: string | null
  /** The product's overall most recent purchase from ANY supplier — offer +
   *  discount are read from whoever sold it last, not necessarily this row's
   *  own supplier. "Buy X get Y" ratio string (e.g. "10+1"), never a percent —
   *  a flat discount only ever shows in pt_discount_pct. */
  pt_offer?: string | null
  pt_discount_pct?: number | null
  /** Identifies the overall-last purchase above, for the hover tooltip. */
  pt_offer_source_supplier_name?: string | null
  pt_offer_source_date?: string | null
}

export interface SupplierRow {
  supplier_code: string
  supplier_name: string | null
  purchase_frequency: number | null
  last_grn_date: string | null
  last_grn_no: string | null
  last_purchase_rate: number | null
  avg_lead_days: number | null
  /** Whether this supplier is eligible for Auto Assign Suppliers at all
   *  (sync.Suppliers.auto_assign, defaults true). */
  auto_assign?: boolean
  /** Auto Assign only commits a batch to this supplier if it would include at
   *  least this many products (sync.Suppliers.min_products, default 2). */
  min_products?: number
}

/** One supplier's Auto Assign settings (sync.Suppliers.auto_assign/
 *  min_products/export_rank) — Supplier Rank & Settings panel row. */
export interface SupplierSettingsRow {
  supplier_code: string
  supplier_name: string | null
  auto_assign: boolean
  min_products: number
  /** null = unranked. Rank 1 = highest priority in Rank-mode Auto Assign. */
  export_rank: number | null
}

/** One row of a parsed Supplier Reply Excel (Export Monitor overhaul) —
 *  matched back to a live assignment via the sheet's hidden Assignment ID
 *  column. `applicable` is false when the row can't be applied (no matching
 *  assignment, or an unrecognized Status value) — surfaced via `warning`. */
export interface SupplierReplyPreviewRow {
  assignment_id: string
  product_name: string | null
  product_code: string | null
  supplier_code: string | null
  assigned_qty: number | null
  status: 'available' | 'partial' | 'not_available' | null
  available_qty: number | null
  warning: string | null
  applicable: boolean
}

export interface SupplierReplyPreview {
  filename: string
  rows: SupplierReplyPreviewRow[]
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

/** Per-supplier Minimum Order config — the raw configured value plus whether
 *  the supplier is actually opted into Optimization (§10/§11: a configured
 *  value alone no longer enrolls a supplier). */
export interface SupplierMinOrderConfig {
  min_order_value: number
  consider_minimum_order: boolean
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
