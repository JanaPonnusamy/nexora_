import { api } from './apiClient'
import type {
  PiAssignResult,
  PiBuildResult,
  PiCharts,
  PiDetail,
  PiGrid,
  PiHistory,
  PiOffers,
  PiResolve,
  PiSummary,
  PiSupplier,
} from '../types/intelligence'

function qs(params: Record<string, string | number | undefined>): string {
  const parts = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== '' && v !== null)
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
  return parts.length ? `?${parts.join('&')}` : ''
}

/** Product Intelligence — the NETWORK procurement engine.
 *
 *  build() consolidates EVERY selected store's VPL (not just the warehouse's)
 *  into one canonical-product grid and calculates what the warehouse must buy for
 *  the whole network. The grid/detail/summary read the backend cache only; the
 *  charts and per-store history are the only on-demand reads and open from the
 *  detail panel. */
export const intelligenceService = {
  build: (tenantId: string, warehouseStoreId: string, storeIds?: string[], by?: string | null) =>
    api.post<PiBuildResult>(`/api/procurement/intelligence/build`, {
      tenant_id: tenantId,
      warehouse_store_id: warehouseStoreId,
      store_ids: storeIds?.length ? storeIds : undefined,
      created_by: by ?? undefined,
    }),

  grid: (tenantId: string, warehouseStoreId?: string, search?: string) =>
    api.get<PiGrid>(
      `/api/procurement/intelligence${qs({
        tenant_id: tenantId,
        warehouse_store_id: warehouseStoreId,
        search,
      })}`,
    ),

  summary: (tenantId: string, warehouseStoreId?: string) =>
    api.get<PiSummary>(
      `/api/procurement/intelligence/summary${qs({
        tenant_id: tenantId,
        warehouse_store_id: warehouseStoreId,
      })}`,
    ),

  detail: (cacheId: string) =>
    api.get<PiDetail>(`/api/procurement/intelligence/${cacheId}`),

  /** Every store's last-N-month chart in ONE call, on a shared month axis. */
  charts: (cacheId: string, months = 4) =>
    api.get<PiCharts>(`/api/procurement/intelligence/${cacheId}/charts${qs({ months })}`),

  /** One store's history — loaded only when that store is opened. */
  history: (cacheId: string, storeId: string, months = 12) =>
    api.get<PiHistory>(
      `/api/procurement/intelligence/${cacheId}/history/${storeId}${qs({ months })}`,
    ),

  /** Refresh EVERY selected store, regenerate each store VPL, then consolidate. */
  refreshBuild: (
    tenantId: string,
    warehouseStoreId: string,
    storeIds: string[],
    by?: string | null,
  ) =>
    api.post<PiBuildResult>(`/api/procurement/intelligence/refresh-build`, {
      tenant_id: tenantId,
      warehouse_store_id: warehouseStoreId,
      store_ids: storeIds,
      created_by: by ?? undefined,
    }),

  /* ---- Mode 2: Supplier Offer Intelligence ------------------------------- */

  suppliers: (tenantId: string, warehouseStoreId: string) =>
    api.get<{ suppliers: PiSupplier[] }>(
      `/api/procurement/intelligence/suppliers${qs({
        tenant_id: tenantId,
        warehouse_store_id: warehouseStoreId,
      })}`,
    ),

  offers: (tenantId: string, warehouseStoreId: string, supplierCode: string, search?: string) =>
    api.get<PiOffers>(
      `/api/procurement/intelligence/supplier-offers${qs({
        tenant_id: tenantId,
        warehouse_store_id: warehouseStoreId,
        supplier_code: supplierCode,
        search,
      })}`,
    ),

  /** Assign preview: the stores that resolve automatically from the picked
   *  warehouse product, and the ones still needing a manual pick. */
  resolveAssignment: (tenantId: string, warehouseStoreId: string, productCode: string) =>
    api.get<PiResolve>(
      `/api/procurement/intelligence/supplier-offers/resolve${qs({
        tenant_id: tenantId,
        warehouse_store_id: warehouseStoreId,
        product_code: productCode,
      })}`,
    ),

  assign: (body: {
    tenant_id: string
    warehouse_store_id: string
    supplier_code: string
    supplier_product_code: string
    supplier_product_name?: string | null
    product_code: string
    store_assignments?: { store_id: string; product_code: string | null }[]
    actor?: string | null
  }) =>
    api.post<PiAssignResult>(`/api/procurement/intelligence/supplier-offers/assign`, body),
}
