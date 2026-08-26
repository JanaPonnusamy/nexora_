import { api } from './apiClient'
import type { ExpiryResult } from '../types/expiryReport'

function qs(params: Record<string, string | number | boolean | undefined>): string {
  const parts = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== '' && v !== null)
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
  return parts.length ? `?${parts.join('&')}` : ''
}

export type NonMovingBasis = 'sold' | 'received'

export interface NonMovingSupplier {
  SupplierCode: string
  SupplierName: string
}

export const nonMovingReportService = {
  data: (
    tenantId: string,
    storeId: string | undefined,
    basis: NonMovingBasis,
    minDays: number,
    maxDays: number | undefined,
    includeNil: boolean,
    supplierCode: string | undefined,
    supplierMode: number,
  ) =>
    api.get<ExpiryResult>(
      `/api/non-moving-report/data${qs({
        tenant_id: tenantId,
        store_id: storeId,
        basis,
        min_days: minDays,
        max_days: maxDays,
        include_nil: includeNil,
        supplier_code: supplierCode,
        supplier_mode: supplierMode,
      })}`,
    ),

  suppliers: (tenantId: string, storeId: string | undefined, supplierMode: number) =>
    api.get<{ rows: NonMovingSupplier[] }>(
      `/api/non-moving-report/suppliers${qs({ tenant_id: tenantId, store_id: storeId, supplier_mode: supplierMode })}`,
    ),
}
