import { api } from './apiClient'
import type {
  SaleAnalysisResult,
  SaleGroupDetail,
  SaleGroupSummary,
  SaleProductOption,
  SaleSupplierOption,
  SaleWindow,
} from '../types/saleAnalysis'

function qs(params: Record<string, string | number | boolean | undefined>): string {
  const parts = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== '' && v !== null)
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
  return parts.length ? `?${parts.join('&')}` : ''
}

export const saleAnalysisService = {
  products: (tenantId: string, storeId: string, q: string, supplierCode?: string, limit = 50) =>
    api
      .get<{ products: SaleProductOption[] }>(
        `/api/sale-analysis/products${qs({ tenant_id: tenantId, store_id: storeId, q, supplier_code: supplierCode, limit })}`,
      )
      .then((r) => r.products),

  suppliers: (tenantId: string, storeId: string, q: string, limit = 30) =>
    api
      .get<{ suppliers: SaleSupplierOption[] }>(
        `/api/sale-analysis/suppliers${qs({ tenant_id: tenantId, store_id: storeId, q, limit })}`,
      )
      .then((r) => r.suppliers),

  listGroups: (tenantId: string) =>
    api
      .get<{ groups: SaleGroupSummary[] }>(`/api/sale-analysis/groups${qs({ tenant_id: tenantId })}`)
      .then((r) => r.groups),

  getGroup: (tenantId: string, groupId: string) =>
    api.get<SaleGroupDetail>(`/api/sale-analysis/groups/${groupId}${qs({ tenant_id: tenantId })}`),

  createGroup: (tenantId: string, groupName: string, productNames: string[]) =>
    api.post<SaleGroupDetail>(`/api/sale-analysis/groups${qs({ tenant_id: tenantId })}`, {
      group_name: groupName,
      product_names: productNames,
    }),

  updateGroup: (tenantId: string, groupId: string, groupName: string, productNames: string[]) =>
    api.put<SaleGroupDetail>(`/api/sale-analysis/groups/${groupId}${qs({ tenant_id: tenantId })}`, {
      group_name: groupName,
      product_names: productNames,
    }),

  deleteGroup: (tenantId: string, groupId: string) =>
    api.delete<{ deleted: boolean }>(`/api/sale-analysis/groups/${groupId}${qs({ tenant_id: tenantId })}`),

  report: (
    tenantId: string,
    storeId: string,
    opts: {
      groupIds?: string[]
      productCodes?: string[]
      window: SaleWindow
      from?: string
      to?: string
      targetDays: number
    },
  ) => {
    const groupParams = (opts.groupIds ?? []).map((g) => `group_id=${encodeURIComponent(g)}`).join('&')
    const rest = qs({
      tenant_id: tenantId,
      store_id: storeId,
      product_codes: (opts.productCodes ?? []).join(','),
      window: opts.window,
      from: opts.from,
      to: opts.to,
      target_days: opts.targetDays,
    })
    const sep = groupParams ? (rest ? '&' : '?') : ''
    return api.get<SaleAnalysisResult>(`/api/sale-analysis/report${rest}${sep}${groupParams}`)
  },
}
