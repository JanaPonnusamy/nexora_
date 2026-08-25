import { api } from './apiClient'
import type { ExpiryStockResult, ExpiryStockSupplier } from '../types/expiryStock'

function qs(params: Record<string, string | number | boolean | undefined>): string {
  const parts = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== '' && v !== null)
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
  return parts.length ? `?${parts.join('&')}` : ''
}

export const expiryStockService = {
  dateBounds: (tenantId: string, storeId: string) =>
    api.get<{ oldest: string | null; newest: string | null }>(
      `/api/expiry-stock/date-bounds${qs({ tenant_id: tenantId, store_id: storeId })}`,
    ),

  suppliers: (tenantId: string, storeId: string) =>
    api.get<{ suppliers: ExpiryStockSupplier[] }>(
      `/api/expiry-stock/suppliers${qs({ tenant_id: tenantId, store_id: storeId })}`,
    ),

  report: (
    tenantId: string,
    storeId: string,
    opts: { supplierCode?: string; from?: string; to?: string; onlyCutting?: boolean },
  ) =>
    api.get<ExpiryStockResult>(
      `/api/expiry-stock/report${qs({
        tenant_id: tenantId,
        store_id: storeId,
        supplier_code: opts.supplierCode,
        from: opts.from,
        to: opts.to,
        only_cutting: opts.onlyCutting ? 'true' : undefined,
      })}`,
    ),
}
