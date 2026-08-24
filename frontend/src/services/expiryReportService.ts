import { api } from './apiClient'
import type { ExpiryResult } from '../types/expiryReport'

function qs(params: Record<string, string | number | undefined>): string {
  const parts = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== '' && v !== null)
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
  return parts.length ? `?${parts.join('&')}` : ''
}

export const expiryReportService = {
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

  supplierAcks: (tenantId: string, storeId: string, supplierCode: string) =>
    api.get<ExpiryResult>(
      `/api/expiry-report/supplier-acks${qs({ tenant_id: tenantId, store_id: storeId, supplier_code: supplierCode })}`,
    ),

  ackProducts: (tenantId: string, storeId: string, ackNumber: string) =>
    api.get<ExpiryResult>(
      `/api/expiry-report/ack-products${qs({ tenant_id: tenantId, store_id: storeId, ack_number: ackNumber })}`,
    ),
}
