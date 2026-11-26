import { API_BASE_URL, ApiError, api } from '../../services/apiClient'
import { pinStorage } from './pinStorage'
import type {
  QuickStockBatchRow,
  QuickStockBillItem,
  QuickStockCore,
  QuickStockCoreBulkResult,
  QuickStockCrossStoreMatch,
  QuickStockGrnItem,
  QuickStockMovementRow,
  QuickStockPurchaseRow,
  QuickStockSalesRow,
  QuickStockSearchResult,
  QuickStockStoreShell,
  QuickStockTenant,
} from './types'

async function call<T>(path: string, pin: string, method: 'GET' | 'POST' = 'GET', body?: unknown): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers: {
        'x-quick-stock-pin': pin,
        ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      },
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    })
  } catch {
    throw new ApiError('Unable to reach the server.', 0)
  }
  if (!response.ok) {
    let detail = response.statusText || 'Request failed'
    try {
      const parsed = await response.json()
      detail = parsed.detail ?? detail
    } catch {
      // no JSON body
    }
    throw new ApiError(detail, response.status)
  }
  return (await response.json()) as T
}

/** MediQ session path. /api/quick-stock/* accepts only x-quick-stock-pin, so
 *  these calls use the stock search the signed-in app already uses. `api`
 *  is the desktop web bridge inside MediQ and attaches the session bearer. */
let sessionBearer = false

function qs(params: Record<string, string | number | null | undefined>): string {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value))
  })
  const text = search.toString()
  return text ? `?${text}` : ''
}

const session = {
  listTenants: async () => {
    const rows = await api.get<{ tenant_id: string; tenant_name: string; is_active?: boolean }[]>('/api/tenants')
    return rows
      .filter((row) => row.is_active !== false)
      .map((row) => ({ tenant_id: row.tenant_id, tenant_name: row.tenant_name }))
  },
  listStores: async (tenantId: string) => {
    const rows = await api.get<{
      store_id: string
      tenant_id: string
      store_code: string | null
      store_name: string | null
      is_active?: boolean
    }[]>('/api/stores')
    return rows
      .filter((row) => row.tenant_id === tenantId && row.is_active !== false)
      .map((row) => ({
        store_id: row.store_id,
        store_code: row.store_code,
        store_name: row.store_name,
      }))
  },
  searchProducts: (tenantId: string, query: string, onlyStock: boolean) =>
    api.get<QuickStockSearchResult>(
      `/api/stock-availability/products/search${qs({ tenant_id: tenantId, q: query, only_stock: onlyStock ? 1 : 0 })}`,
    ),
  productCore: (tenantId: string, storeId: string, productCode: string, months = 4) =>
    api.get<QuickStockCore>(
      `/api/stock-availability/products/core${qs({ tenant_id: tenantId, store_id: storeId, product: productCode, months })}`,
    ),
  productCoreBulk: (tenantId: string, items: { store_id: string; product_code: string }[], months = 4) =>
    api.post<QuickStockCoreBulkResult>('/api/stock-availability/products/core/bulk', {
      tenant_id: tenantId,
      months,
      items,
    }),
  /** Sales/Purchase toggle, every store in one request: only `mode`'s
   * transactions are fetched (plus batches/movement, always needed for the
   * chart) -- the inactive type is never queried. */
  productCoreBulkSplit: (
    tenantId: string,
    items: { store_id: string; product_code: string }[],
    mode: 'sales' | 'purchase',
    months = 4,
  ) =>
    api.post<QuickStockCoreBulkResult>('/api/stock-availability/products/core/bulk-split', {
      tenant_id: tenantId,
      months,
      mode,
      items,
    }),
  // Mode-independent (Chart always needs these, regardless of Sales/Purchase).
  productBatches: (tenantId: string, storeId: string, productCode: string) =>
    api.get<QuickStockBatchRow[]>(
      `/api/stock-availability/products/batches${qs({ tenant_id: tenantId, store_id: storeId, product: productCode })}`,
    ),
  productMovement: (tenantId: string, storeId: string, productCode: string, months = 4) =>
    api.get<QuickStockMovementRow[]>(
      `/api/stock-availability/products/movement${qs({ tenant_id: tenantId, store_id: storeId, product: productCode, months })}`,
    ),
  // Mode-specific: only ever fetched for the active toggle (never both).
  productPurchases: (tenantId: string, storeId: string, productCode: string) =>
    api.get<QuickStockPurchaseRow[]>(
      `/api/stock-availability/products/purchases${qs({ tenant_id: tenantId, store_id: storeId, product: productCode })}`,
    ),
  productSales: (tenantId: string, storeId: string, productCode: string) =>
    api.get<QuickStockSalesRow[]>(
      `/api/stock-availability/products/sales${qs({ tenant_id: tenantId, store_id: storeId, product: productCode })}`,
    ),
  billItems: (tenantId: string, storeId: string, billNo: string, billDate?: string | null) =>
    api.get<QuickStockBillItem[]>(
      `/api/stock-availability/products/bill${qs({ tenant_id: tenantId, store_id: storeId, bill_no: billNo, bill_date: billDate })}`,
    ),
  purchaseBill: (tenantId: string, storeId: string, grnNo: string, grnDate?: string | null) =>
    api.get<QuickStockGrnItem[]>(
      `/api/stock-availability/bills/purchase${qs({ tenant_id: tenantId, store_id: storeId, grn_no: grnNo, grn_date: grnDate })}`,
    ),
  crossStoreMatch: (
    tenantId: string,
    sourceStoreId: string,
    sourceProductCode: string,
    sourceProductName: string,
    targetStoreIds: string[],
  ) =>
    api.post<{ results: QuickStockCrossStoreMatch[] }>('/api/stock-availability/products/sync-selection', {
      tenant_id: tenantId,
      source_store_id: sourceStoreId,
      source_product_code: sourceProductCode,
      source_product_name: sourceProductName,
      target_store_ids: targetStoreIds,
    }),
}

export const quickStockService = {
  /** MediQ sets this before the page loads data. The public kiosk leaves it off. */
  useSessionBearer(enabled: boolean) {
    sessionBearer = enabled
  },

  /** Verifies a candidate PIN against the server; throws ApiError(401) if wrong. */
  verifyPin: (pin: string) => call<{ ok: boolean }>('/api/quick-stock/verify', pin, 'POST'),

  listTenants: () =>
    sessionBearer
      ? session.listTenants()
      : call<QuickStockTenant[]>('/api/quick-stock/tenants', pinStorage.get()),

  listStores: (tenantId: string) =>
    sessionBearer
      ? session.listStores(tenantId)
      : call<QuickStockStoreShell[]>(`/api/quick-stock/stores?tenant_id=${encodeURIComponent(tenantId)}`, pinStorage.get()),

  searchProducts: (tenantId: string, query: string, onlyStock: boolean) =>
    sessionBearer
      ? session.searchProducts(tenantId, query, onlyStock)
      : call<QuickStockSearchResult>(
          `/api/quick-stock/products/search?tenant_id=${encodeURIComponent(tenantId)}&q=${encodeURIComponent(query)}&only_stock=${onlyStock ? 1 : 0}`,
          pinStorage.get(),
        ),

  productCore: (tenantId: string, storeId: string, productCode: string, months = 4) =>
    sessionBearer
      ? session.productCore(tenantId, storeId, productCode, months)
      : call<QuickStockCore>(
          `/api/quick-stock/products/core?tenant_id=${encodeURIComponent(tenantId)}&store_id=${encodeURIComponent(storeId)}&product=${encodeURIComponent(productCode)}&months=${months}`,
          pinStorage.get(),
        ),

  /** One request for every store's chart+sales+purchase data, instead of one
   * request per store -- N concurrent per-store requests were contending on
   * the same heavy query and leaving most stores stuck on "Loading...". */
  productCoreBulk: (tenantId: string, items: { store_id: string; product_code: string }[], months = 4) =>
    sessionBearer
      ? session.productCoreBulk(tenantId, items, months)
      : call<QuickStockCoreBulkResult>(
          '/api/quick-stock/products/core/bulk',
          pinStorage.get(),
          'POST',
          { tenant_id: tenantId, items, months },
        ),

  /** Sales/Purchase toggle, every store in one request -- fetches ONLY the
   * active mode's transactions, never both. */
  productCoreBulkSplit: (
    tenantId: string,
    items: { store_id: string; product_code: string }[],
    mode: 'sales' | 'purchase',
    months = 4,
  ) =>
    sessionBearer
      ? session.productCoreBulkSplit(tenantId, items, mode, months)
      : call<QuickStockCoreBulkResult>(
          '/api/quick-stock/products/core/bulk-split',
          pinStorage.get(),
          'POST',
          { tenant_id: tenantId, items, mode, months },
        ),

  /** Mode-independent: the Chart always needs batches + movement regardless
   * of the Sales/Purchase toggle, so these are fetched once per store and
   * never re-fetched on a toggle switch. */
  productBatches: (tenantId: string, storeId: string, productCode: string) =>
    sessionBearer
      ? session.productBatches(tenantId, storeId, productCode)
      : call<QuickStockBatchRow[]>(
          `/api/quick-stock/products/batches?tenant_id=${encodeURIComponent(tenantId)}&store_id=${encodeURIComponent(storeId)}&product=${encodeURIComponent(productCode)}`,
          pinStorage.get(),
        ),

  productMovement: (tenantId: string, storeId: string, productCode: string, months = 4) =>
    sessionBearer
      ? session.productMovement(tenantId, storeId, productCode, months)
      : call<QuickStockMovementRow[]>(
          `/api/quick-stock/products/movement?tenant_id=${encodeURIComponent(tenantId)}&store_id=${encodeURIComponent(storeId)}&product=${encodeURIComponent(productCode)}&months=${months}`,
          pinStorage.get(),
        ),

  /** Mode-specific: fetched ONLY for the active toggle (Sales XOR Purchase),
   * never both -- this is what actually stops the inactive type from ever
   * being requested, unlike productCore's bundled result. */
  productPurchases: (tenantId: string, storeId: string, productCode: string) =>
    sessionBearer
      ? session.productPurchases(tenantId, storeId, productCode)
      : call<QuickStockPurchaseRow[]>(
          `/api/quick-stock/products/purchases?tenant_id=${encodeURIComponent(tenantId)}&store_id=${encodeURIComponent(storeId)}&product=${encodeURIComponent(productCode)}`,
          pinStorage.get(),
        ),

  productSales: (tenantId: string, storeId: string, productCode: string) =>
    sessionBearer
      ? session.productSales(tenantId, storeId, productCode)
      : call<QuickStockSalesRow[]>(
          `/api/quick-stock/products/sales?tenant_id=${encodeURIComponent(tenantId)}&store_id=${encodeURIComponent(storeId)}&product=${encodeURIComponent(productCode)}`,
          pinStorage.get(),
        ),

  billItems: (tenantId: string, storeId: string, billNo: string, billDate?: string | null) =>
    sessionBearer
      ? session.billItems(tenantId, storeId, billNo, billDate)
      : call<QuickStockBillItem[]>(
          `/api/quick-stock/products/bill?tenant_id=${encodeURIComponent(tenantId)}&store_id=${encodeURIComponent(storeId)}&bill_no=${encodeURIComponent(billNo)}${billDate ? `&bill_date=${encodeURIComponent(billDate)}` : ''}`,
          pinStorage.get(),
        ),

  purchaseBill: (tenantId: string, storeId: string, grnNo: string, grnDate?: string | null) =>
    sessionBearer
      ? session.purchaseBill(tenantId, storeId, grnNo, grnDate)
      : call<QuickStockGrnItem[]>(
          `/api/quick-stock/products/grn?tenant_id=${encodeURIComponent(tenantId)}&store_id=${encodeURIComponent(storeId)}&grn_no=${encodeURIComponent(grnNo)}${grnDate ? `&grn_date=${encodeURIComponent(grnDate)}` : ''}`,
          pinStorage.get(),
        ),

  /** Resolves the equivalent product in each target store via the real
   * Product Mapping matcher — fixes stores silently dropping out of the
   * all-stores view when their product name differs by even whitespace. */
  crossStoreMatch: (
    tenantId: string,
    sourceStoreId: string,
    sourceProductCode: string,
    sourceProductName: string,
    targetStoreIds: string[],
  ) =>
    sessionBearer
      ? session.crossStoreMatch(tenantId, sourceStoreId, sourceProductCode, sourceProductName, targetStoreIds)
      : call<{ results: QuickStockCrossStoreMatch[] }>(
          '/api/quick-stock/products/match',
          pinStorage.get(),
          'POST',
          {
            tenant_id: tenantId,
            source_store_id: sourceStoreId,
            source_product_code: sourceProductCode,
            source_product_name: sourceProductName,
            target_store_ids: targetStoreIds,
          },
        ),
}
