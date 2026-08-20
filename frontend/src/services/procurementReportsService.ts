import { api } from './apiClient'
import type {
  PharmacyCompareResponse,
  PharmacyDashboardResponse,
  PharmacyReportSource,
  PharmacyStoreAnalysisResponse,
} from '../types/procurementReports'

function qs(params: Record<string, string | number | undefined>): string {
  const parts = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== '' && v !== null)
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
  return parts.length ? `?${parts.join('&')}` : ''
}

export const procurementReportsService = {
  dashboard: (tenantId: string, fromMonth: string, toMonth: string, source: PharmacyReportSource) =>
    api.get<PharmacyDashboardResponse>(
      `/api/procurement/reports/dashboard${qs({
        tenant_id: tenantId,
        from_month: fromMonth,
        to_month: toMonth,
        source,
      })}`,
    ),

  storeAnalysis: (tenantId: string, storeId: string, fromMonth: string, toMonth: string, source: PharmacyReportSource) =>
    api.get<PharmacyStoreAnalysisResponse>(
      `/api/procurement/reports/store-analysis${qs({
        tenant_id: tenantId,
        store_id: storeId,
        from_month: fromMonth,
        to_month: toMonth,
        source,
      })}`,
    ),

  dashboardExcel: (tenantId: string, fromMonth: string, toMonth: string, source: PharmacyReportSource) =>
    api.blob(
      `/api/procurement/reports/dashboard/export.xlsx${qs({
        tenant_id: tenantId,
        from_month: fromMonth,
        to_month: toMonth,
        source,
      })}`,
    ),

  storeAnalysisExcel: (tenantId: string, storeId: string, fromMonth: string, toMonth: string, source: PharmacyReportSource) =>
    api.blob(
      `/api/procurement/reports/store-analysis/export.xlsx${qs({
        tenant_id: tenantId,
        store_id: storeId,
        from_month: fromMonth,
        to_month: toMonth,
        source,
      })}`,
    ),

  compare: (tenantId: string, monthA: string, monthB: string, source: PharmacyReportSource) =>
    api.get<PharmacyCompareResponse>(
      `/api/procurement/reports/compare${qs({
        tenant_id: tenantId,
        month_a: monthA,
        month_b: monthB,
        source,
      })}`,
    ),

  compareExcel: (tenantId: string, monthA: string, monthB: string, source: PharmacyReportSource) =>
    api.blob(
      `/api/procurement/reports/compare/export.xlsx${qs({
        tenant_id: tenantId,
        month_a: monthA,
        month_b: monthB,
        source,
      })}`,
    ),
}
