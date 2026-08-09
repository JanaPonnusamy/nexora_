import { api } from './apiClient'
import type {
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
  LegacyDbHealth,
  LegacyDbRecovery,
} from '../types/legacyOrder'

const BASE = '/api/legacy-order'

export const legacyOrderService = {
  listStores: (activeOnly = true) =>
    api.get<LegacyStore[]>(`${BASE}/stores?active_only=${activeOnly}`),

  listTables: () => api.get<LegacyTable[]>(`${BASE}/tables`),

  defaults: () => api.get<{ min_days: number; max_days: number }>(`${BASE}/defaults`),

  startSync: (storeName: string, tables?: string[]) =>
    api.post<{ job_id: string }>(`${BASE}/sync`, {
      store_name: storeName,
      tables: tables ?? null,
    }),

  startOrderProcess: (
    storeName: string,
    minDays: number,
    maxDays: number,
    mode: OrderMode,
  ) =>
    api.post<{ job_id: string }>(`${BASE}/order-process`, {
      store_name: storeName,
      min_days: minDays,
      max_days: maxDays,
      mode,
    }),

  startStockUpdate: (storeName: string, sourceStoreName = 'NMW') =>
    api.post<{ job_id: string }>(`${BASE}/stock-update`, {
      store_name: storeName,
      source_store_name: sourceStoreName,
    }),

  getJob: (jobId: string) => api.get<LegacyJob>(`${BASE}/jobs/${jobId}`),

  orders: (storeName: string) =>
    api.get<OrderRow[]>(`${BASE}/orders/${encodeURIComponent(storeName)}`),

  updateOrderQty: (storeName: string, productCode: number, orderQty: number) =>
    api.patch<{ store_name: string; product_code: number; order_qty: number }>(
      `${BASE}/orders/${encodeURIComponent(storeName)}/${productCode}`,
      { order_qty: orderQty },
    ),

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

  updateQtyCheck: (storeName: string, productCode: number, orderQty: number) =>
    api.patch<QtyCheckUpdateResult>(
      `${BASE}/qty-check/${encodeURIComponent(storeName)}/${productCode}`,
      { order_qty: orderQty },
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
}
