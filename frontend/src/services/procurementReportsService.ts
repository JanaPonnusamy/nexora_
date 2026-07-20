import { api } from './apiClient'
import type {
  PharmacyCompareResponse,
  PharmacyDashboardResponse,
  PharmacyStoreAnalysisResponse,
} from '../types/procurementReports'

function qs(params: Record<string, string | number | undefined>): string {
  const parts = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== '' && v !== null)
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
  return parts.length ? `?${parts.join('&')}` : ''
}

export const procurementReportsService = {
  dashboard: (tenantId: string, fromMonth: string, toMonth: string) =>
    api.get<PharmacyDashboardResponse>(
      `/api/procurement/reports/dashboard${qs({
        tenant_id: tenantId,
        from_month: fromMonth,
        to_month: toMonth,
      })}`,
    ),

  storeAnalysis: (tenantId: string, storeId: string, fromMonth: string, toMonth: string) =>
    api.get<PharmacyStoreAnalysisResponse>(
      `/api/procurement/reports/store-analysis${qs({
        tenant_id: tenantId,
        store_id: storeId,
        from_month: fromMonth,
        to_month: toMonth,
      })}`,
    ),

  dashboardExcel: (tenantId: string, fromMonth: string, toMonth: string) =>
    api.blob(
      `/api/procurement/reports/dashboard/export.xlsx${qs({
        tenant_id: tenantId,
        from_month: fromMonth,
        to_month: toMonth,
      })}`,
    ),

  storeAnalysisExcel: (tenantId: string, storeId: string, fromMonth: string, toMonth: string) =>
    api.blob(
      `/api/procurement/reports/store-analysis/export.xlsx${qs({
        tenant_id: tenantId,
        store_id: storeId,
        from_month: fromMonth,
        to_month: toMonth,
      })}`,
    ),

  compare: (tenantId: string, monthA: string, monthB: string) =>
    api.get<PharmacyCompareResponse>(
      `/api/procurement/reports/compare${qs({
        tenant_id: tenantId,
        month_a: monthA,
        month_b: monthB,
      })}`,
    ),

  compareExcel: (tenantId: string, monthA: string, monthB: string) =>
    api.blob(
      `/api/procurement/reports/compare/export.xlsx${qs({
        tenant_id: tenantId,
        month_a: monthA,
        month_b: monthB,
      })}`,
    ),
}
