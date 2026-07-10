import { api } from './apiClient'
import type {
  Assignment,
  CloseCycleResult,
  Cycle,
  DecisionDetail,
  ExportBatch,
  GrnResult,
  ManualProduct,
  MappingTarget,
  OptimizationAuditRow,
  OptimizationMoveResult,
  OptimizationResult,
  PendingPage,
  Refresh,
  SupplierMinOrderConfig,
  SupplierQueue,
  SupplierRecommendation,
  SupplierRow,
  SupplierStockPreview,
  SupplierStockRow,
  WorkspaceFilters,
  WorkspaceItem,
  WorkspacePage,
  WorkspaceSummary,
} from '../types/procurement'

function qs(params: Record<string, string | number | undefined>): string {
  const parts = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== '' && v !== null)
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
  return parts.length ? `?${parts.join('&')}` : ''
}

export const procurementService = {
  refreshes: (tenantId: string, storeId?: string) =>
    api
      .get<{ items: Refresh[] }>(
        `/api/procurement/vpl${qs({ tenant_id: tenantId, store_id: storeId, page_size: 200 })}`,
      )
      .then((r) => r.items),

  workspace: (tenantId: string, refreshId: string, f: WorkspaceFilters, signal?: AbortSignal) =>
    api.get<WorkspacePage>(
      `/api/procurement/refreshes/${refreshId}/workspace${qs({
        tenant_id: tenantId,
        search: f.search,
        item_status: f.item_status,
        movement_class: f.movement_class,
        stock_status: f.stock_status,
        sort_by: f.sort_by,
        sort_dir: f.sort_dir,
        page: f.page,
        page_size: f.page_size,
      })}`,
      signal,
    ),

  // Footer counts (Total / Pending Review / Assigned / Finalized / Skipped),
  // computed server-side. Scope matches the grid's base load (search +
  // movement_class only) — Purchase Value stays client-computed, see
  // WorkspaceSummary's doc comment.
  workspaceSummary: (tenantId: string, refreshId: string, search?: string, movementClass?: string) =>
    api.get<WorkspaceSummary>(
      `/api/procurement/refreshes/${refreshId}/workspace/summary${qs({
        tenant_id: tenantId, search, movement_class: movementClass,
      })}`,
    ),

  setFinalQty: (tenantId: string, orderItemId: string, finalQty: number, reason: string | null, by: string | null) =>
    api.put<WorkspaceItem>(
      `/api/procurement/order-items/${orderItemId}/final-qty${qs({ tenant_id: tenantId })}`,
      { final_qty: finalQty, override_reason: reason, reviewed_by: by },
    ),

  // Single working item, fresh from the server — used to reconcile just one
  // row (e.g. after removing its supplier assignment) without a full
  // workspace reload (§23).
  getOrderItem: (tenantId: string, orderItemId: string) =>
    api.get<WorkspaceItem>(`/api/procurement/order-items/${orderItemId}${qs({ tenant_id: tenantId })}`),

  restoreSuggested: (tenantId: string, orderItemId: string, by: string | null) =>
    api.post<WorkspaceItem>(
      `/api/procurement/order-items/${orderItemId}/restore-suggested${qs({ tenant_id: tenantId })}`,
      { reviewed_by: by },
    ),

  skip: (tenantId: string, orderItemId: string, reason: string, by: string | null) =>
    api.post<WorkspaceItem>(
      `/api/procurement/order-items/${orderItemId}/skip${qs({ tenant_id: tenantId })}`,
      { skip_reason: reason, reviewed_by: by },
    ),

  restore: (tenantId: string, orderItemId: string, by: string | null) =>
    api.post<WorkspaceItem>(
      `/api/procurement/order-items/${orderItemId}/restore${qs({ tenant_id: tenantId })}`,
      { reviewed_by: by },
    ),

  // Assignment Deferred (Space Bar) — excludes the row from Auto/Bulk
  // Assignment while keeping its Final Qty. Un-defer reuses `restore` above
  // (the backend's restore endpoint now accepts both skipped and deferred).
  defer: (tenantId: string, orderItemId: string, by: string | null) =>
    api.post<WorkspaceItem>(
      `/api/procurement/order-items/${orderItemId}/defer${qs({ tenant_id: tenantId })}`,
      { reviewed_by: by },
    ),

  supplierQueue: (tenantId: string, orderItemId: string, limit = 3) =>
    api.get<SupplierQueue>(
      `/api/procurement/order-items/${orderItemId}/supplier-queue${qs({ tenant_id: tenantId, limit })}`,
    ),

  // Batched supplier recommendations for every working item in a refresh
  // (one round-trip — powers the Product Grid supplier icons).
  supplierRecommendations: (tenantId: string, refreshId: string, limit = 5) =>
    api
      .get<{ items: SupplierRecommendation[] }>(
        `/api/procurement/refreshes/${refreshId}/supplier-recommendations${qs({ tenant_id: tenantId, limit })}`,
      )
      .then((r) => r.items),

  // Order-item ids the supplier has purchase history for (Supplier Purchasing
  // mode shows exactly these products).
  supplierProducts: (tenantId: string, refreshId: string, supplierCode: string) =>
    api
      .get<{ order_item_ids: string[] }>(
        `/api/procurement/refreshes/${refreshId}/supplier-products${qs({ tenant_id: tenantId, supplier_code: supplierCode })}`,
      )
      .then((r) => r.order_item_ids),

  assignments: (tenantId: string, orderItemId: string) =>
    api
      .get<{ items: Assignment[] }>(
        `/api/procurement/order-items/${orderItemId}/assignments${qs({ tenant_id: tenantId })}`,
      )
      .then((r) => r.items),

  // Every live assignment for the whole Refresh, one round-trip — the Supplier
  // Queue build uses this instead of one /assignments call per assigned item.
  refreshAssignments: (tenantId: string, refreshId: string) =>
    api
      .get<{ items: Assignment[] }>(
        `/api/procurement/refreshes/${refreshId}/assignments${qs({ tenant_id: tenantId })}`,
      )
      .then((r) => r.items),

  assign: (tenantId: string, orderItemId: string, supplierCode: string, qty: number, by: string | null) =>
    api.post(
      `/api/procurement/order-items/${orderItemId}/assignments${qs({ tenant_id: tenantId })}`,
      { supplier_code: supplierCode, qty, created_by: by },
    ),

  bulkAssign: (tenantId: string, supplierCode: string, orderItemIds: string[], by: string | null) =>
    api.post<{
      assigned: number
      skipped: number
      results: { order_item_id: string; status: 'assigned' | 'skipped'; qty?: number; reason?: string }[]
    }>(
      `/api/procurement/assignments/bulk${qs({ tenant_id: tenantId })}`,
      { supplier_code: supplierCode, items: orderItemIds.map((id) => ({ order_item_id: id })), created_by: by },
    ),

  changeSupplier: (tenantId: string, assignmentId: string, supplierCode: string, by: string | null) =>
    api.put(
      `/api/procurement/assignments/${assignmentId}/supplier${qs({ tenant_id: tenantId })}`,
      { supplier_code: supplierCode, updated_by: by },
    ),

  removeAssignment: (tenantId: string, assignmentId: string, by: string | null) =>
    api.delete(
      `/api/procurement/assignments/${assignmentId}${qs({ tenant_id: tenantId, deleted_by: by ?? undefined })}`,
    ),

  exportRefresh: (tenantId: string, refreshId: string, by: string, assignmentIds?: string[], supplierCode?: string) =>
    api.post<{ export_batch_number: string; exported_count: number; supplier_count: number }>(
      `/api/procurement/refreshes/${refreshId}/export${qs({ tenant_id: tenantId })}`,
      { exported_by: by, assignment_ids: assignmentIds, supplier_code: supplierCode },
    ),

  exportHistory: (tenantId: string, refreshId: string) =>
    api
      .get<{ batches: ExportBatch[] }>(
        `/api/procurement/refreshes/${refreshId}/export-history${qs({ tenant_id: tenantId })}`,
      )
      .then((r) => r.batches),

  // --- Sprint 3: GRN, pending, decision explorer, cycle close ---
  submitGrn: (tenantId: string, refreshId: string, lastGrn: string, by: string | null) =>
    api.post<GrnResult>(
      `/api/procurement/refreshes/${refreshId}/grn${qs({ tenant_id: tenantId })}`,
      { last_grn_number: lastGrn, submitted_by: by },
    ),

  pending: (tenantId: string, refreshId: string) =>
    api.get<PendingPage>(
      `/api/procurement/refreshes/${refreshId}/pending${qs({ tenant_id: tenantId, page_size: 300 })}`,
    ),

  adjustPending: (tenantId: string, orderItemId: string, remaining: number, by: string | null) =>
    api.put(
      `/api/procurement/order-items/${orderItemId}/pending${qs({ tenant_id: tenantId })}`,
      { remaining_qty: remaining, reviewed_by: by },
    ),

  skipPending: (tenantId: string, orderItemId: string, by: string | null) =>
    api.post(
      `/api/procurement/order-items/${orderItemId}/pending/skip${qs({ tenant_id: tenantId })}`,
      { reviewed_by: by },
    ),

  carryForwardPending: (tenantId: string, orderItemId: string, by: string | null) =>
    api.post(
      `/api/procurement/order-items/${orderItemId}/pending/carry-forward${qs({ tenant_id: tenantId })}`,
      { reviewed_by: by },
    ),

  finalizePending: (tenantId: string, refreshId: string, by: string | null) =>
    api.post<{ finalized: number }>(
      `/api/procurement/refreshes/${refreshId}/pending/finalize${qs({ tenant_id: tenantId })}`,
      { reviewed_by: by },
    ),

  // Bulk pending action (carry / skip / finalize) over many items — powers
  // bulk processing and supplier-wise carry in the Pending tab.
  bulkPending: (
    tenantId: string,
    refreshId: string,
    action: 'carry' | 'skip' | 'finalize',
    orderItemIds: string[],
    by: string | null,
  ) =>
    api.post<{ action: string; processed: number }>(
      `/api/procurement/refreshes/${refreshId}/pending/bulk${qs({ tenant_id: tenantId })}`,
      { action, order_item_ids: orderItemIds, reviewed_by: by },
    ),

  // Server-generated pending report (.xlsx); returns the Blob for download.
  pendingReport: (tenantId: string, refreshId: string) =>
    api.blob(`/api/procurement/refreshes/${refreshId}/pending/report${qs({ tenant_id: tenantId })}`),

  addManualItem: (tenantId: string, refreshId: string, code: string, name: string, qty: number, by: string | null) =>
    api.post(
      `/api/procurement/refreshes/${refreshId}/manual-items${qs({ tenant_id: tenantId })}`,
      { product_code: code, product_name: name, qty, created_by: by },
    ),

  // Manual Add Product search over the real Product Master (sync.Products).
  searchProducts: (tenantId: string, storeId: string, q: string, limit = 25) =>
    api
      .get<{ products: ManualProduct[] }>(
        `/api/procurement/products/search${qs({ tenant_id: tenantId, store_id: storeId, q, limit })}`,
      )
      .then((r) => r.products),

  // Supplier directory search (Mode 2 — pick a supplier to purchase for).
  searchSuppliers: (tenantId: string, q: string, storeId?: string, limit = 20) =>
    api
      .get<{ suppliers: SupplierRow[] }>(
        `/api/procurement/suppliers/search${qs({ tenant_id: tenantId, q, store_id: storeId, limit })}`,
      )
      .then((r) => r.suppliers),

  supplierStats: (tenantId: string, supplierCode: string, storeId?: string) =>
    api.get(`/api/procurement/suppliers/${supplierCode}/stats${qs({ tenant_id: tenantId, store_id: storeId })}`),

  // Supplier Live Stock (supplier_stock ∩ SupplierProductMatch ∩ current VPL).
  supplierStock: (
    tenantId: string,
    refreshId: string,
    supplierCode: string,
    search?: string,
    onlyAvailable = true,
  ) =>
    api
      .get<{ items: SupplierStockRow[] }>(
        `/api/procurement/refreshes/${refreshId}/supplier-stock${qs({
          tenant_id: tenantId,
          supplier_code: supplierCode,
          search,
          only_available: onlyAvailable ? 'true' : 'false',
        })}`,
      )
      .then((r) => r.items),

  // --- Supplier Live Stock: Excel import + header mapping ---
  supplierStockMapping: (tenantId: string, storeId: string, supplierCode: string) =>
    api.get<{ mapping: Record<string, string>; targets: MappingTarget[] }>(
      `/api/procurement/supplier-stock/mapping${qs({ tenant_id: tenantId, store_id: storeId, supplier_code: supplierCode })}`,
    ),

  supplierStockPreview: (tenantId: string, storeId: string, supplierCode: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.upload<SupplierStockPreview>(
      `/api/procurement/supplier-stock/preview${qs({ tenant_id: tenantId, store_id: storeId, supplier_code: supplierCode })}`,
      form,
    )
  },

  supplierStockImport: (
    tenantId: string,
    storeId: string,
    supplierCode: string,
    file: File,
    mapping: Record<string, string>,
    by: string | null,
  ) => {
    const form = new FormData()
    form.append('file', file)
    form.append('mapping', JSON.stringify(mapping))
    return api.upload<{ inserted: number; product_codes_resolved: number }>(
      `/api/procurement/supplier-stock/import${qs({ tenant_id: tenantId, store_id: storeId, supplier_code: supplierCode, created_by: by ?? undefined })}`,
      form,
    )
  },

  decision: (tenantId: string, orderItemId: string) =>
    api.get<DecisionDetail>(
      `/api/procurement/order-items/${orderItemId}/decision${qs({ tenant_id: tenantId })}`,
    ),

  // --- Supplier Order Optimization (the stage between Auto Assignment and Export) ---

  // Below-minimum suppliers + the lowest-value suggested moves to fix them.
  optimization: (
    tenantId: string,
    refreshId: string,
    opts?: { priceTolerance?: number; useLiveStock?: boolean },
  ) =>
    api.get<OptimizationResult>(
      `/api/procurement/refreshes/${refreshId}/optimization${qs({
        tenant_id: tenantId,
        price_tolerance: opts?.priceTolerance,
        use_live_stock: opts?.useLiveStock === false ? 'false' : undefined,
      })}`,
    ),

  // Apply accepted suggestion(s) — Accept / Accept All.
  applyOptimization: (
    tenantId: string,
    refreshId: string,
    moves: { assignment_id: string; to_supplier: string }[],
    by: string | null,
    reason: 'auto' | 'manual' = 'auto',
  ) =>
    api.post<OptimizationMoveResult>(
      `/api/procurement/refreshes/${refreshId}/optimization/apply${qs({ tenant_id: tenantId })}`,
      { moves, reason, applied_by: by },
    ),

  // Manual Move — move one product to another supplier (§8).
  manualMove: (
    tenantId: string,
    refreshId: string,
    assignmentId: string,
    toSupplier: string,
    by: string | null,
  ) =>
    api.post(
      `/api/procurement/refreshes/${refreshId}/optimization/manual-move${qs({ tenant_id: tenantId })}`,
      { assignment_id: assignmentId, to_supplier: toSupplier, moved_by: by },
    ),

  optimizationAudit: (tenantId: string, refreshId: string) =>
    api
      .get<{ moves: OptimizationAuditRow[] }>(
        `/api/procurement/refreshes/${refreshId}/optimization/audit${qs({ tenant_id: tenantId })}`,
      )
      .then((r) => r.moves),

  // Per-supplier Minimum Order Value config.
  minOrders: (tenantId: string, storeId: string) =>
    api
      .get<{ min_orders: Record<string, number> }>(
        `/api/procurement/suppliers/min-orders${qs({ tenant_id: tenantId, store_id: storeId })}`,
      )
      .then((r) => r.min_orders),

  setMinOrder: (
    tenantId: string,
    supplierCode: string,
    storeId: string,
    minOrderValue: number,
    by: string | null,
  ) =>
    api.put(
      `/api/procurement/suppliers/${supplierCode}/min-order${qs({ tenant_id: tenantId })}`,
      { store_id: storeId, min_order_value: minOrderValue, updated_by: by },
    ),

  // Both min_order_value + consider_minimum_order per supplier, one round
  // trip — powers the Minimum Order Settings panel.
  minOrderConfig: (tenantId: string, storeId: string) =>
    api
      .get<{ config: Record<string, SupplierMinOrderConfig> }>(
        `/api/procurement/suppliers/min-order-config${qs({ tenant_id: tenantId, store_id: storeId })}`,
      )
      .then((r) => r.config),

  setConsiderMinimumOrder: (
    tenantId: string,
    supplierCode: string,
    storeId: string,
    considerMinimumOrder: boolean,
    by: string | null,
  ) =>
    api.put(
      `/api/procurement/suppliers/${supplierCode}/consider-minimum-order${qs({ tenant_id: tenantId })}`,
      { store_id: storeId, consider_minimum_order: considerMinimumOrder, updated_by: by },
    ),

  // Close a cycle. End GRN / End Sale Bill are auto-read from synced data on the
  // server (no manual entry). Pass force=true to confirm closing while pending
  // items still exist (they are cleared, not carried) — the first call without
  // force returns `pending_confirm` when pending remains.
  closeCycle: (tenantId: string, cycleId: string, by: string | null, force = false) =>
    api.post<CloseCycleResult>(
      `/api/procurement/cycles/${cycleId}/close${qs({ tenant_id: tenantId })}`,
      { closed_by: by, force },
    ),

  // --- Admin: Cycle & Refresh Management (lifecycle) ---
  cycles: (tenantId: string, storeId?: string, status?: string) =>
    api
      .get<{ items: Cycle[] }>(
        `/api/procurement/cycles${qs({ tenant_id: tenantId, store_id: storeId, status, page_size: 200 })}`,
      )
      .then((r) => r.items),

  openCycle: (payload: {
    tenant_id: string
    name: string
    store_id: string
    description?: string
    start_grn_number?: string
    start_sale_bill_number?: string
    created_by: string
  }) => api.post<Cycle>(`/api/procurement/cycles/open`, payload),

  refreshesForCycle: (tenantId: string, cycleId: string) =>
    api
      .get<{ items: Refresh[] }>(
        `/api/procurement/vpl${qs({ tenant_id: tenantId, cycle_id: cycleId, page_size: 200 })}`,
      )
      .then((r) => r.items),

  generateRefresh: (
    tenantId: string,
    cycleId: string,
    payload: {
      snapshot_name?: string
      rolling_days?: number
      min_days: number
      max_days: number
      created_by?: string | null
    },
  ) =>
    api.post<{ refresh_id: string; generated_product_count: number; working_item_count: number }>(
      `/api/procurement/cycles/${cycleId}/refreshes${qs({ tenant_id: tenantId })}`,
      payload,
    ),
}
