import { api } from './apiClient'
import type { ExpiryResult } from '../types/expiryReport'

function qs(params: Record<string, string | number | undefined>): string {
  const parts = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== '' && v !== null)
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
  return parts.length ? `?${parts.join('&')}` : ''
}

export type ExpiryStatus = 'all' | 'received' | 'pending' | 'rejected'
export type ExpiryGroupBy = 'summary' | 'ack' | 'month' | 'supplier' | 'product'

export interface ExpirySupplier {
  SupplierCode: string
  SupplierName: string
}

export const expiryReportService = {
  dateBounds: (tenantId: string, storeId?: string, supplierCode?: string) =>
    api.get<{ oldest_pending: string | null }>(
      `/api/expiry-report/date-bounds${qs({ tenant_id: tenantId, store_id: storeId, supplier_code: supplierCode })}`,
    ),

  suppliers: (tenantId: string, storeId?: string) =>
    api.get<{ suppliers: ExpirySupplier[] }>(
      `/api/expiry-report/suppliers${qs({ tenant_id: tenantId, store_id: storeId })}`,
    ),

  data: (
    tenantId: string,
    storeId: string | undefined,
    from: string,
    to: string,
    status: ExpiryStatus,
    groupBy: ExpiryGroupBy,
    supplierCode?: string,
  ) =>
    api.get<ExpiryResult>(
      `/api/expiry-report/data${qs({ tenant_id: tenantId, store_id: storeId, from, to, status, group_by: groupBy, supplier_code: supplierCode })}`,
    ),

  storeSummary: (tenantId: string) =>
    api.get<ExpiryResult>(`/api/expiry-report/store-summary${qs({ tenant_id: tenantId })}`),

  supplierSummary: (tenantId: string, storeId: string) =>
    api.get<ExpiryResult>(
      `/api/expiry-report/supplier-summary${qs({ tenant_id: tenantId, store_id: storeId })}`,
    ),

  supplierPending: (tenantId: string, storeId: string, supplierCode: string) =>
    api.get<ExpiryResult>(
      `/api/expiry-report/supplier-pending${qs({ tenant_id: tenantId, store_id: storeId, supplier_code: supplierCode })}`,
    ),

  pendingMonths: (tenantId: string, storeId: string) =>
    api.get<ExpiryResult>(
      `/api/expiry-report/pending-months${qs({ tenant_id: tenantId, store_id: storeId })}`,
    ),

  pendingByMonth: (tenantId: string, storeId: string, month: string) =>
    api.get<ExpiryResult>(
      `/api/expiry-report/pending-by-month${qs({ tenant_id: tenantId, store_id: storeId, month })}`,
    ),

  supplierAcks: (tenantId: string, storeId: string, supplierCode: string) =>
    api.get<ExpiryResult>(
      `/api/expiry-report/supplier-acks${qs({ tenant_id: tenantId, store_id: storeId, supplier_code: supplierCode })}`,
    ),

  ackProducts: (tenantId: string, storeId: string, ackNumber: string) =>
    api.get<ExpiryResult>(
      `/api/expiry-report/ack-products${qs({ tenant_id: tenantId, store_id: storeId, ack_number: ackNumber })}`,
    ),
}
