import { api } from './apiClient'
import type { ReportDef, ReportParams, ReportResult, SupplierOption } from '../types/reports'

function qs(params: Record<string, string | number | undefined>): string {
  const parts = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== '' && v !== null)
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
  return parts.length ? `?${parts.join('&')}` : ''
}

export const reportsService = {
  catalog: () =>
    api.get<{ reports: ReportDef[] }>('/api/reports').then((r) => r.reports),

  suppliers: (tenantId: string, storeId: string, q: string, limit = 30) =>
    api
      .get<{ suppliers: SupplierOption[] }>(
        `/api/reports/suppliers${qs({ tenant_id: tenantId, store_id: storeId, q, limit })}`,
      )
      .then((r) => r.suppliers),

  run: (reportKey: string, tenantId: string, storeId: string, params: ReportParams) =>
    api.get<ReportResult>(
      `/api/reports/${reportKey}${qs({
        tenant_id: tenantId,
        store_id: storeId,
        from: params.from,
        to: params.to,
        dwell_days: params.dwell_days,
        supplier_code: params.supplier_code,
        division_code: params.division_code,
      })}`,
    ),
}
