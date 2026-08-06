import { api } from './apiClient'
import type { StockCheckResult } from '../types/stockCheckReport'

export const stockCheckReportService = {
  getRows: (tenantId: string, storeId: string, sublocationFrom: string, sublocationTo: string) =>
    api.get<StockCheckResult>(
      `/api/stock-check-report/rows?tenant_id=${encodeURIComponent(tenantId)}&store_id=${encodeURIComponent(storeId)}` +
        `&sublocation_from=${encodeURIComponent(sublocationFrom)}&sublocation_to=${encodeURIComponent(sublocationTo)}`,
    ),
  searchSublocations: (tenantId: string, storeId: string, q: string) =>
    api.get<{ sublocations: string[] }>(
      `/api/stock-check-report/sublocations?tenant_id=${encodeURIComponent(tenantId)}&store_id=${encodeURIComponent(storeId)}&q=${encodeURIComponent(q)}`,
    ),
}
