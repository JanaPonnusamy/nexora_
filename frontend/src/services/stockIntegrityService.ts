import { api } from './apiClient'
import type { StockIntegrityRepairResult, StockIntegrityResult } from '../types/stockIntegrity'

export const stockIntegrityService = {
  getReport: (tenantId: string, storeId: string) =>
    api.get<StockIntegrityResult>(
      `/api/stock-integrity/report?tenant_id=${encodeURIComponent(tenantId)}&store_id=${encodeURIComponent(storeId)}`,
    ),
  repair: (tenantId: string, storeId: string) =>
    api.post<StockIntegrityRepairResult>(
      `/api/stock-integrity/repair?tenant_id=${encodeURIComponent(tenantId)}&store_id=${encodeURIComponent(storeId)}`,
      {},
    ),
}
