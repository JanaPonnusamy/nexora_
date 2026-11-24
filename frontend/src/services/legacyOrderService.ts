import { api } from './apiClient'
import type {
  AssignedOrderRow,
  AssignResult,
  LegacyJob,
  LegacyStore,
  LegacyTable,
  MonthlyStatRow,
  OrderHistoryRow,
  OrderMode,
  OrderRow,
  PreviousOrder,
  PreviousOrderComparison,
  PreviousOrderSupplier,
  PurchaseDetailRow,
  QtyCheckRow,
  QtyCheckUpdateResult,
  SalesDetailRow,
  SupplierComparison,
  SupplierComparisonProduct,
  SupplierListItem,
  SupplierOrderMode,
  WorkspaceOrderRow,
  LegacyDbHealth,
  LegacyDbRecovery,
  OrderWorkflowAuditEntry,
  OrderWorkflowSummary,
  PendingOrderRow,
  QtyCheckConfirmation,
  ResetPendingResult,
  RestorableOrderPreview,
  RestoreResult,
  MessageSetting,
  MessageType,
  OrderEntryAutomation,
  PmOrderEntryRecent,
  PmOrderEntryState,
  PmOrderEntrySubmitResult,
  PmOrderQueueRow,
  PmOrderType,
  OrderGapReview,
  PendingOrderItem,
} from '../types/legacyOrder'

const BASE = '/api/legacy-order'

export interface OrderCacheMonitorRow {
  store_name: string
  exists: boolean
  cache_path: string
  file_created_at?: string
  file_age_seconds?: number
  built_at?: string | null
  schema_version?: string | null
  row_count?: number
  pending_writeback_count?: number
  unsynced_row_count?: number
  last_writeback_at?: string | null
  last_writeback_status?: 'ok' | 'failed' | null
  last_writeback_error?: string | null
  connection_status?: 'ok' | 'broken'
}

export type CompareMode = 'PREVIOUS_PENDING' | 'TODAY' | 'NONE' | 'HO'

export interface ReceivedNotOrdered {
  store_name: string
  since: string | null
  product_type: string
  rows: Array<{
    grn_no: number; grn_date: string | null; supplier_code: string | null; supplier_name: string | null
    product_code: number; product_name: string | null; qty: number; free_qty: number
    purchase_price: number; mrp: number; product_type: string
  }>
}

export type OrderEngine = 'LEGACY' | 'RULEBOOK'

export const legacyOrderService = {
  listStores: (activeOnly = true) =>
    api.get<LegacyStore[]>(`${BASE}/stores?active_only=${activeOnly}`),

  listTables: () => api.get<LegacyTable[]>(`${BASE}/tables`),

  receivedNotOrdered: (storeName: string, productType = 'pharma') =>
    api.get<ReceivedNotOrdered>(`${BASE}/orders/${encodeURIComponent(storeName)}/received-not-ordered?product_type=${encodeURIComponent(productType)}`),

  defaults: () => api.get<{
    min_days: number; max_days: number
    recency_days: number; warehouse_recency_days: number; warehouse_stores: string[]
    warehouse_source: string | null
  }>(`${BASE}/defaults`),

  // OrderNMC mirror: send this store's current OrderNMC data to every remote
  // OrderNMC that carries it, on that PC agent's next pull.
  pushToRemoteOrderNmc: (storeName: string) =>
    api.post<{ pushed: { target_id: number; tables_due: number; interval_seconds: number }[] }>(
      '/api/ordernmc-mirror/v1/admin/push', { store_name: storeName }),

  startSync: (storeName: string, tables?: string[]) =>
    api.post<{ job_id: string }>(`${BASE}/sync`, {
      store_name: storeName,
      tables: tables ?? null,
    }),

  // confirmed acknowledges the pending-supplier-assignment warning -- an
  // ordinary confirmation, not a privileged override. The server always
  // recomputes order_id/count fresh and rejects (409) if they no longer
  // match confirmedOrderId/confirmedCount.
  // confirmStaleOrder is a SEPARATE acknowledgement of the stale-current-
  // order warning (see service.StaleCurrentOrder) -- independent of
  // `confirm` above so confirming one warning never silently waves through
  // the other.
  // Order engine per store: LEGACY (ported VB.NET SQL) or RULEBOOK
  // (Procurement rule book). Both write the same OrderNMC tables.
  getOrderEngine: (storeName: string) =>
    api.get<{
      store_name: string; engine: OrderEngine; engines: OrderEngine[]; rulebook_params: Record<string, number>
      compare_today_previous?: boolean; compare_mode?: CompareMode
      order_defaults: { min_days: number | null; max_days: number | null; recency_days: number | null }
      mode: OrderMode
    }>(`${BASE}/engine/${encodeURIComponent(storeName)}`),
  // Per-store "Compare today's previous order": every Order Process then
  // compares the new order with the store's earlier order from today.
  setCompareToday: (storeName: string, enabled: boolean) =>
    api.put<{ store_name: string; compare_today_previous: boolean }>(
      `${BASE}/engine/${encodeURIComponent(storeName)}/compare-today`, { enabled }),
  // The store's saved Compare mode (owner ruling 2026-11-05).
  setCompareMode: (storeName: string, mode: CompareMode) =>
    api.put<{ store_name: string; compare_mode: CompareMode }>(
      `${BASE}/engine/${encodeURIComponent(storeName)}/compare-mode`, { mode }),
  setOrderEngine: (storeName: string, engine: OrderEngine) =>
    api.put<{ store_name: string; engine: OrderEngine }>(`${BASE}/engine/${encodeURIComponent(storeName)}`, { engine }),
  // Fixed per-store Source for the evening/scheduled run (owner request
  // 2026-11-24): independent of whatever the live grid's Source shows.
  setOrderMode: (storeName: string, mode: OrderMode | null) =>
    api.put<{ store_name: string; mode: OrderMode | null }>(
      `${BASE}/engine/${encodeURIComponent(storeName)}/mode`, { mode }),
  // Fixed per-store Min/Max/Recency override; any field left null falls back
  // to the global/warehouse default again. (getOrderEngine's response already
  // carries this as `.order_defaults` -- no separate GET needed.)
  setOrderDefaults: (storeName: string, payload: { min_days: number | null; max_days: number | null; recency_days: number | null }) =>
    api.put<{ store_name: string; min_days: number | null; max_days: number | null; recency_days: number | null }>(
      `${BASE}/engine/${encodeURIComponent(storeName)}/order-defaults`, payload),

  // Evening (second) order schedule -- every ticked store, one after another,
  // from a fixed start time, each with its saved/fixed settings (not the live
  // grid). Settings live centrally in OrderNMC so web and every desktop
  // client share one schedule.
  eveningSchedule: () =>
    api.get<{
      enabled: boolean; run_at: string; stores: string[] | null
      last_run_date: string | null; last_run_started_at: string | null; last_run_finished_at: string | null
      last_run: { trigger: string; started_at: string; finished_at: string | null
        stores: { store_name: string; status: string; job_id?: string; rows?: number; error?: string
          compare?: { order_id: number; affected_rows: number } }[] } | null
      next_run: string | null; running: boolean; catch_up_minutes: number
    }>(`${BASE}/schedule/evening`),
  saveEveningSchedule: (payload: { enabled: boolean; run_at: string; stores: string[] | null }) =>
    api.put(`${BASE}/schedule/evening`, payload),
  runEveningNow: () => api.post<{ started: boolean; stores: string[] }>(`${BASE}/schedule/evening/run`, {}),
  // Dry run: legacy vs rule-book order as Excel; writes nothing.
  compareEnginesXlsx: (storeName: string, recencyDays?: number) =>
    api.blob(`${BASE}/engine/${encodeURIComponent(storeName)}/compare.xlsx${recencyDays ? `?recency_days=${recencyDays}` : ''}`),
  startOrderProcess: (
    storeName: string,
    minDays: number,
    maxDays: number,
    mode: OrderMode,
    confirm?: { orderId: number; count: number },
    confirmStaleOrder = false,
    recencyDays?: number,
    // The store's last sale bill / last GRN off its POS: the server syncs,
    // checks both reached OrderNMC, and only then generates the order.
    checkpoint?: { lastBill: string; lastGrn: string },
    // PREVIOUS_PENDING / TODAY / NONE / HO; undefined = the store's saved mode.
    compareMode?: CompareMode,
  ) =>
    api.post<{ job_id: string }>(`${BASE}/order-process`, {
      store_name: storeName,
      min_days: minDays,
      max_days: maxDays,
      recency_days: recencyDays ?? null,
      mode,
      confirmed: Boolean(confirm),
      confirmed_order_id: confirm?.orderId ?? null,
      confirmed_count: confirm?.count ?? null,
      confirmed_stale_order: confirmStaleOrder,
      last_bill: checkpoint?.lastBill.trim() || null,
      last_grn: checkpoint?.lastGrn.trim() || null,
      compare_mode: compareMode ?? null,
    }),

  restorableOrderPreview: (storeName: string, orderId: number) =>
    api.get<RestorableOrderPreview>(
      `${BASE}/orders/${encodeURIComponent(storeName)}/restorable/${orderId}`,
    ),

  restoreBackupOrder: (storeName: string, orderId: number) =>
    api.post<RestoreResult>(`${BASE}/orders/${encodeURIComponent(storeName)}/restore`, { order_id: orderId }),

  qtyCheckConfirmation: (storeName: string) =>
    api.get<QtyCheckConfirmation>(`${BASE}/orders/${encodeURIComponent(storeName)}/qty-check-confirmation`),

  startStockUpdate: (storeName: string, sourceStoreName?: string) =>
    api.post<{ job_id: string }>(`${BASE}/stock-update`, {
      store_name: storeName,
      source_store_name: sourceStoreName,
    }),

  startStockUpdateAll: (sourceStoreName?: string) =>
    api.post<{
      source_store: string
      started: { store_name: string; job_id: string; supplier_code: string | null; before_count: number | null }[]
      skipped: { store_name: string; reason: string }[]
    }>(
      `${BASE}/stock-update-all`,
      { source_store_name: sourceStoreName },
    ),

  getJob: (jobId: string) => api.get<LegacyJob>(`${BASE}/jobs/${jobId}`),

  supplierStockCount: (storeName: string, supplierCode: string) =>
    api.get<{ store_name: string; supplier_code: string; count: number }>(
      `${BASE}/stores/${encodeURIComponent(storeName)}/supplier-stock-count?supplier_code=${encodeURIComponent(supplierCode)}`,
    ),

  orders: (storeName: string) =>
    api.get<OrderRow[]>(`${BASE}/orders/${encodeURIComponent(storeName)}`),

  updateOrderQty: (storeName: string, productCode: number, orderQty: number) =>
    api.patch<{ store_name: string; product_code: number; order_qty: number }>(
      `${BASE}/orders/${encodeURIComponent(storeName)}/${productCode}`,
      { order_qty: orderQty },
    ),

  orderWorkflow: (storeName: string) =>
    api.get<OrderWorkflowSummary>(
      `${BASE}/orders/${encodeURIComponent(storeName)}/workflow`,
    ),

  orderWorkflowAudit: (storeName: string, limit = 30) =>
    api.get<OrderWorkflowAuditEntry[]>(
      `${BASE}/orders/${encodeURIComponent(storeName)}/workflow/audit?limit=${limit}`,
    ),

  finalizeOrder: (storeName: string, note?: string) =>
    api.post<OrderWorkflowSummary>(
      `${BASE}/orders/${encodeURIComponent(storeName)}/workflow/finalize`,
      { note: note || null },
    ),

  reopenOrder: (storeName: string, note?: string) =>
    api.post<OrderWorkflowSummary>(
      `${BASE}/orders/${encodeURIComponent(storeName)}/workflow/reopen`,
      { note: note || null },
    ),

  suppliers: (storeName: string, search = '') =>
    api.get<SupplierListItem[]>(
      `${BASE}/suppliers/${encodeURIComponent(storeName)}?search=${encodeURIComponent(search)}`,
    ),

  ordersBySupplier: (storeName: string, supplierCode: string, mode: SupplierOrderMode) =>
    api.get<WorkspaceOrderRow[]>(
      `${BASE}/orders/${encodeURIComponent(storeName)}/by-supplier`
      + `?supplier_code=${encodeURIComponent(supplierCode)}&mode=${mode}`,
    ),

  // Stock-mode exportable row count for this store/supplier -- what Export
  // always acts on, independent of whichever History/Live Stock tab is
  // currently displayed. Drives the Export button's label/enabled state
  // without fetching the full stock grid.
  ordersBySupplierExportCount: (storeName: string, supplierCode: string) =>
    api.get<{ count: number }>(
      `${BASE}/orders/${encodeURIComponent(storeName)}/by-supplier/export-count`
      + `?supplier_code=${encodeURIComponent(supplierCode)}`,
    ),

  assignedOrders: (storeName: string, supplierCode: string) =>
    api.get<AssignedOrderRow[]>(
      `${BASE}/orders/${encodeURIComponent(storeName)}/assigned`
      + `?supplier_code=${encodeURIComponent(supplierCode)}`,
    ),

  assignSupplier: (
    storeName: string, productCode: number, supplierCode: string, supplierName: string,
  ) =>
    api.post<AssignResult>(
      `${BASE}/orders/${encodeURIComponent(storeName)}/${productCode}/assign`,
      { supplier_code: supplierCode, supplier_name: supplierName },
    ),

  // Bulk-assigns every OrderQty>0 row for this supplier (no per-product
  // Assign/Unassign), then returns the Order Workspace Excel export (or a
  // .zip of "Part N of M" files when splitSize splits it). Filename +
  // assigned-count come back in response headers.
  exportOrder: (
    storeName: string, supplierCode: string, supplierName: string,
    mode: SupplierOrderMode, splitSize = 0,
  ) =>
    api
      .postBlobMeta(`${BASE}/orders/${encodeURIComponent(storeName)}/export`, {
        supplier_code: supplierCode,
        supplier_name: supplierName,
        mode,
        split_size: splitSize,
      })
      .then(({ blob, headers }) => {
        const disposition = headers.get('Content-Disposition') ?? ''
        const match = /filename="?([^"]+)"?/.exec(disposition)
        return {
          blob,
          filename: match?.[1] ?? `${supplierName} ${storeName}.xlsx`,
          exportedCount: Number(headers.get('X-Exported-Count') ?? 0),
        }
      }),

  previousOrders: (storeName: string) =>
    api.get<PreviousOrder[]>(`${BASE}/previous-orders/${encodeURIComponent(storeName)}`),

  comparePreviousOrder: (storeName: string, orderId: number) =>
    api.post<PreviousOrderComparison>(`${BASE}/compare-previous-order`, {
      store_name: storeName,
      order_id: orderId,
    }),

  previousOrderSuppliers: (storeName: string, orderId: number) =>
    api.get<PreviousOrderSupplier[]>(
      `${BASE}/previous-orders/${encodeURIComponent(storeName)}/${orderId}/suppliers`,
    ),

  previousOrderSupplierProducts: (
    storeName: string, orderId: number, supplierCode: string,
  ) => api.get<SupplierComparisonProduct[]>(
    `${BASE}/previous-orders/${encodeURIComponent(storeName)}/${orderId}/suppliers/${encodeURIComponent(supplierCode)}/products`,
  ),

  comparePreviousOrderSupplier: (storeName: string, orderId: number, supplierCode: string) =>
    api.post<SupplierComparison>(`${BASE}/compare-previous-order/supplier`, {
      store_name: storeName,
      order_id: orderId,
      supplier_code: supplierCode,
    }),

  qtyCheckRows: (storeName: string) =>
    api.get<QtyCheckRow[]>(`${BASE}/qty-check/${encodeURIComponent(storeName)}`),

  resetPendingQtyCheck: (storeName: string) =>
    api.post<ResetPendingResult>(`${BASE}/qty-check/${encodeURIComponent(storeName)}/reset-pending`, {}),

  updateQtyCheck: (storeName: string, productCode: number, orderQty: number) =>
    api.patch<QtyCheckUpdateResult>(
      `${BASE}/qty-check/${encodeURIComponent(storeName)}/${productCode}`,
      { order_qty: orderQty },
    ),

  pendingOrderRows: (storeName: string, productType = 'All') =>
    api.get<PendingOrderRow[]>(
      `${BASE}/pending-order/${encodeURIComponent(storeName)}?product_type=${encodeURIComponent(productType)}`,
    ),

  qtyCheckPurchaseDetails: (storeName: string, productCode: number, mode: OrderMode) =>
    api.get<PurchaseDetailRow[]>(
      `${BASE}/qty-check/${encodeURIComponent(storeName)}/${productCode}/purchase-details?mode=${mode}`,
    ),

  qtyCheckSalesDetails: (storeName: string, productCode: number, mode: OrderMode) =>
    api.get<SalesDetailRow[]>(
      `${BASE}/qty-check/${encodeURIComponent(storeName)}/${productCode}/sales-details?mode=${mode}`,
    ),

  qtyCheckMonthlyStats: (storeName: string, productCode: number, mode: OrderMode) =>
    api.get<MonthlyStatRow[]>(
      `${BASE}/qty-check/${encodeURIComponent(storeName)}/${productCode}/monthly-stats?mode=${mode}`,
    ),

  qtyCheckOrderHistory: (storeName: string, productCode: number) =>
    api.get<OrderHistoryRow[]>(
      `${BASE}/qty-check/${encodeURIComponent(storeName)}/${productCode}/order-history`,
    ),

  dbHealth: () => api.get<LegacyDbHealth>(`${BASE}/db/health`),

  dbRecover: () => api.post<LegacyDbRecovery>(`${BASE}/db/recover`, {}),

  dbEmergencyRepair: () =>
    api.post<LegacyDbRecovery>(`${BASE}/db/emergency-repair`, { confirm: true }),

  // ----- PM Order Entry: last bill/GRN submit, automated queue, automation +
  // message-type settings (Purchase Manager, store-scoped; owner ruling
  // 2026-11-05 / automation added later the same cycle). -----
  pmOrderEntry: (storeName: string) =>
    api.get<PmOrderEntryState>(`${BASE}/orders/${encodeURIComponent(storeName)}/order-entry`),

  pmSubmitOrderEntry: (
    storeName: string,
    payload: { lastBill: string; lastGrn: string; orderType: PmOrderType; confirmed?: boolean },
  ) =>
    api.post<PmOrderEntrySubmitResult>(`${BASE}/orders/${encodeURIComponent(storeName)}/order-entry`, {
      last_bill: payload.lastBill.trim(),
      last_grn: payload.lastGrn.trim(),
      order_type: payload.orderType,
      confirmed: Boolean(payload.confirmed),
    }),

  // Plain "most recent N" GRN + sale-bill grids for the PM's own visual
  // verification -- replaces the old received-not-ordered report on this
  // screen (see repository.recent_grns/recent_sale_bills).
  pmOrderEntryRecent: (storeName: string, limit = 50) =>
    api.get<PmOrderEntryRecent>(
      `${BASE}/orders/${encodeURIComponent(storeName)}/order-entry/recent?limit=${limit}`,
    ),

  pmOrderEntryQueue: (storeName: string) =>
    api.get<PmOrderQueueRow | { status: null }>(`${BASE}/orders/${encodeURIComponent(storeName)}/order-entry/queue`),

  getOrderEntryAutomation: (storeName: string) =>
    api.get<OrderEntryAutomation>(`${BASE}/orders/${encodeURIComponent(storeName)}/automation`),

  setOrderEntryAutomation: (
    storeName: string,
    payload: { automated_order_enabled: boolean; production_mode: boolean; min_delay_seconds: number; max_delay_seconds: number },
  ) =>
    api.put<OrderEntryAutomation>(`${BASE}/orders/${encodeURIComponent(storeName)}/automation`, payload),

  // ----- Order Gap Review: reconciliation since the store's last placed
  // order, plus the standing pending-reminder list. -----
  getGapReview: (storeName: string, orderId?: number) =>
    api.get<OrderGapReview>(
      `${BASE}/orders/${encodeURIComponent(storeName)}/gap-review${orderId != null ? `?order_id=${orderId}` : ''}`,
    ),

  addPendingItem: (
    storeName: string,
    body: { product_code: number; product_name?: string | null; order_id?: number | null; qty?: number | null; note?: string | null },
  ) =>
    api.post<PendingOrderItem>(`${BASE}/orders/${encodeURIComponent(storeName)}/gap-review/pending`, body),

  clearPendingItem: (storeName: string, itemId: number) =>
    api.delete<{ cleared: true; id: number }>(`${BASE}/orders/${encodeURIComponent(storeName)}/gap-review/pending/${itemId}`),

  getMessageSettings: (storeName: string) =>
    api.get<MessageSetting[]>(`${BASE}/orders/${encodeURIComponent(storeName)}/message-settings`),

  setMessageSetting: (
    storeName: string,
    messageType: MessageType,
    payload: { enabled: boolean; targets: { name: string; kind: 'group' | 'contact' }[] },
  ) =>
    api.put<MessageSetting>(
      `${BASE}/orders/${encodeURIComponent(storeName)}/message-settings/${encodeURIComponent(messageType)}`,
      payload,
    ),

  // ---- Order cache monitor (Sync > Order Cache Monitor) ----
  orderCacheMonitorAll: () => api.get<{ stores: OrderCacheMonitorRow[] }>(`${BASE}/order-cache/monitor`),

  orderCacheMonitorOne: (storeName: string) =>
    api.get<OrderCacheMonitorRow>(`${BASE}/order-cache/${encodeURIComponent(storeName)}/monitor`),

  orderCacheForcePull: (storeName: string) =>
    api.post<{ store_name: string; cache_path: string }>(
      `${BASE}/order-cache/${encodeURIComponent(storeName)}/force-pull`,
      {},
    ),

  orderCacheForcePush: (storeName: string) =>
    api.post<{ ok: boolean; applied: number; error: string | null }>(
      `${BASE}/order-cache/${encodeURIComponent(storeName)}/force-push`,
      {},
    ),

  orderCacheExport: (storeName: string) => api.blob(`${BASE}/order-cache/${encodeURIComponent(storeName)}/export`),

  orderCacheSend: (storeName: string, channel: 'whatsapp' | 'email') =>
    api.post<{ ok: boolean; channel: string; error?: string }>(
      `${BASE}/order-cache/${encodeURIComponent(storeName)}/send?channel=${channel}`,
      {},
    ),

  orderCacheImport: (storeName: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.upload<{ store_name: string; imported: boolean; writeback: { ok: boolean; applied: number; error: string | null } }>(
      `${BASE}/order-cache/${encodeURIComponent(storeName)}/import`,
      form,
    )
  },
}
