import { api } from './apiClient'
import type {
  LabelSearchResult,
  BoxSearchResult,
  BoxProductResult,
  ProductBatchResult,
} from '../types/labelExporter'

const BASE = '/api/label-exporter'

interface SearchProductsParams {
  tenantId: string
  storeId: string
  q?: string
  startsWith?: string
  unitDescription?: string
  boxNumber?: string
  stockFilter?: string
  onlyNullSublocation?: boolean
  onlySaleUnitGtOne?: boolean
}

export const labelExporterService = {
  searchProducts: ({
    tenantId,
    storeId,
    q = '',
    startsWith = '',
    unitDescription = '',
    boxNumber = '',
    stockFilter = 'all',
    onlyNullSublocation = false,
    onlySaleUnitGtOne = false,
  }: SearchProductsParams) => {
    const params = new URLSearchParams({
      tenant_id: tenantId,
      store_id: storeId,
    })
    if (q) params.set('q', q)
    if (startsWith) params.set('starts_with', startsWith)
    if (unitDescription) params.set('unit_description', unitDescription)
    if (boxNumber) params.set('box_number', boxNumber)
    if (stockFilter !== 'all') params.set('stock_filter', stockFilter)
    if (onlyNullSublocation) params.set('only_null_sublocation', '1')
    if (onlySaleUnitGtOne) params.set('only_sale_unit_gt_one', '1')
    return api.get<LabelSearchResult>(`${BASE}/products/search?${params}`)
  },

  searchBoxes: (tenantId: string, storeId: string, q = '', startsWith = '') => {
    const params = new URLSearchParams({ tenant_id: tenantId, store_id: storeId })
    if (q) params.set('q', q)
    if (startsWith) params.set('starts_with', startsWith)
    return api.get<BoxSearchResult>(`${BASE}/boxes/search?${params}`)
  },

  getBoxProducts: (tenantId: string, storeId: string, boxNumber: string) =>
    api.get<BoxProductResult>(
      `${BASE}/boxes/products?${new URLSearchParams({ tenant_id: tenantId, store_id: storeId, box_number: boxNumber })}`,
    ),

  getProductBatches: (tenantId: string, storeId: string, productCode: string) =>
    api.get<ProductBatchResult>(
      `${BASE}/products/batches?${new URLSearchParams({ tenant_id: tenantId, store_id: storeId, product_code: productCode })}`,
    ),
}
