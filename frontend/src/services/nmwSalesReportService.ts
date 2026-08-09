import { api } from './apiClient'
import type {
  BillKey,
  NmwSalesBillItem,
  NmwSalesBillList,
  NmwStoreCustCode,
} from '../types/nmwSalesReport'

const base = '/api/nmw-sales-report'

export const nmwSalesReportService = {
  listBills: (
    tenantId: string,
    opts: { storeId?: string; status?: string; dateFrom?: string; dateTo?: string } = {},
  ) => {
    const q = new URLSearchParams({ tenant_id: tenantId })
    if (opts.storeId) q.set('store_id', opts.storeId)
    if (opts.status) q.set('status', opts.status)
    if (opts.dateFrom) q.set('date_from', opts.dateFrom)
    if (opts.dateTo) q.set('date_to', opts.dateTo)
    return api.get<NmwSalesBillList>(`${base}/bills?${q.toString()}`)
  },

  billItems: (tenantId: string, billNo: string, billDate: string) =>
    api.get<{ items: NmwSalesBillItem[] }>(
      `${base}/bills/${encodeURIComponent(billNo)}/items?tenant_id=${encodeURIComponent(tenantId)}&bill_date=${encodeURIComponent(billDate)}`,
    ),

  approve: (tenantId: string, bills: BillKey[], status: 'approved' | 'pending' = 'approved') =>
    api.post<{ approved: number; status: string }>(`${base}/bills/approve`, {
      tenant_id: tenantId,
      bills,
      status,
    }),

  listStoreCustCodes: (tenantId: string) =>
    api.get<{ stores: NmwStoreCustCode[] }>(
      `${base}/store-cust-codes?tenant_id=${encodeURIComponent(tenantId)}`,
    ),

  setStoreCustCode: (tenantId: string, storeId: string, custCode: string, codeType: 'cust' | 'transfer' = 'cust') =>
    api.put<{ updated: number }>(
      `${base}/store-cust-codes/${encodeURIComponent(storeId)}?tenant_id=${encodeURIComponent(tenantId)}&cust_code=${encodeURIComponent(custCode)}&code_type=${codeType}`,
      {},
    ),

  importLegacyCustCodes: (tenantId: string) =>
    api.post<{ imported: number; skipped: string[]; reason?: string }>(
      `${base}/store-cust-codes/import-legacy?tenant_id=${encodeURIComponent(tenantId)}`,
      {},
    ),

  autoMatchCustCodes: (tenantId: string, apply = true) =>
    api.post<{
      matched: number
      unmatched?: string[]
      applied?: boolean
      reason?: string
      assignments: { store_code: string; store_name: string; customer_code: string; customer_name: string; score: number }[]
    }>(`${base}/store-cust-codes/auto-match?tenant_id=${encodeURIComponent(tenantId)}&apply=${apply}`, {}),
}
