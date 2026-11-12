import { API_BASE_URL, ApiError } from '../../services/apiClient'
import { pinStorage } from './pinStorage'
import type { QuickStockCore, QuickStockSearchResult, QuickStockTenant } from './types'

async function call<T>(path: string, pin: string): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      headers: { 'x-quick-stock-pin': pin },
    })
  } catch {
    throw new ApiError('Unable to reach the server.', 0)
  }
  if (!response.ok) {
    let detail = response.statusText || 'Request failed'
    try {
      const body = await response.json()
      detail = body.detail ?? detail
    } catch {
      // no JSON body
    }
    throw new ApiError(detail, response.status)
  }
  return (await response.json()) as T
}

export const quickStockService = {
  /** Verifies a candidate PIN against the server; throws ApiError(401) if wrong. */
  verifyPin: (pin: string) => call<{ ok: boolean }>('/api/quick-stock/verify', pin),

  listTenants: () => call<QuickStockTenant[]>('/api/quick-stock/tenants', pinStorage.get()),

  searchProducts: (tenantId: string, query: string, onlyStock: boolean) =>
    call<QuickStockSearchResult>(
      `/api/quick-stock/products/search?tenant_id=${encodeURIComponent(tenantId)}&q=${encodeURIComponent(query)}&only_stock=${onlyStock ? 1 : 0}`,
      pinStorage.get(),
    ),

  productCore: (tenantId: string, storeId: string, productCode: string) =>
    call<QuickStockCore>(
      `/api/quick-stock/products/core?tenant_id=${encodeURIComponent(tenantId)}&store_id=${encodeURIComponent(storeId)}&product=${encodeURIComponent(productCode)}`,
      pinStorage.get(),
    ),
}
