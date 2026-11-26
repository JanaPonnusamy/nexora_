import { api } from './apiClient'
import type { StockCheckFilters, StockCheckResult, StockCheckSupplierOption } from '../types/stockCheckReport'

function qs(params: Record<string, string | number | boolean | undefined>): string {
  const parts = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== '' && v !== null)
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
  return parts.length ? `?${parts.join('&')}` : ''
}

export const stockCheckReportService = {
  getRows: (tenantId: string, storeId: string, filters: StockCheckFilters) =>
    api.get<StockCheckResult>(
      `/api/stock-check-report/rows${qs({
        tenant_id: tenantId,
        store_id: storeId,
        sublocation_from: filters.sublocationFrom,
        sublocation_to: filters.sublocationTo,
        product_code_from: filters.productCodeFrom,
        product_code_to: filters.productCodeTo,
        product_name: filters.productName,
        supplier_code: filters.supplierCode,
        unit_description: filters.unitDescription,
        batch_code: filters.batchCode,
        expiry_from: filters.expiryFrom,
        expiry_to: filters.expiryTo,
        min_stock: filters.minStock,
        max_stock: filters.maxStock,
        include_zero_stock: filters.includeZeroStock,
        include_negative_stock: filters.includeNegativeStock,
      })}`,
    ),
  searchSublocations: (tenantId: string, storeId: string, q: string) =>
    api.get<{ sublocations: string[] }>(
      `/api/stock-check-report/sublocations${qs({ tenant_id: tenantId, store_id: storeId, q })}`,
    ),
  listSuppliers: (tenantId: string, storeId: string) =>
    api.get<{ suppliers: StockCheckSupplierOption[] }>(
      `/api/stock-check-report/suppliers${qs({ tenant_id: tenantId, store_id: storeId })}`,
    ),
  listUnits: (tenantId: string, storeId: string) =>
    api.get<{ units: string[] }>(
      `/api/stock-check-report/units${qs({ tenant_id: tenantId, store_id: storeId })}`,
    ),
}
