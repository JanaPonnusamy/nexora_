import { api } from './apiClient'
import type {
  LabelSearchResult,
  BoxSearchResult,
  BoxProductResult,
  ProductBatchResult,
  LabelReviewUpdateRequest,
  LabelTrendResult,
  LabelPurchaseResult,
  LabelSaleResult,
  LabelAssignRequest,
  LabelAssignResult,
  LabelQueueResult,
  UnitDescriptionMode,
  ReviewStatusFilter,
  IncludeLabel,
} from '../types/labelExporter'

const BASE = '/api/label-exporter'

interface SearchProductsParams {
  tenantId: string
  storeId: string
  q?: string
  startsWith?: string
  unitDescription?: string
  unitDescriptionMode?: UnitDescriptionMode
  boxNumber?: string
  stockFilter?: string
  onlyNullSublocation?: boolean
  onlySaleUnitGtOne?: boolean
  reviewStatus?: ReviewStatusFilter
}

function scope(tenantId: string, storeId: string) {
  return new URLSearchParams({ tenant_id: tenantId, store_id: storeId })
}

export const labelExporterService = {
  searchProducts: ({
    tenantId,
    storeId,
    q = '',
    startsWith = '',
    unitDescription = '',
    unitDescriptionMode = 'contains',
    boxNumber = '',
    stockFilter = 'all',
    onlyNullSublocation = false,
    onlySaleUnitGtOne = false,
    reviewStatus = '',
  }: SearchProductsParams) => {
    const params = scope(tenantId, storeId)
    if (q) params.set('q', q)
    if (startsWith) params.set('starts_with', startsWith)
    if (unitDescription) params.set('unit_description', unitDescription)
    if (unitDescriptionMode !== 'contains') params.set('unit_description_mode', unitDescriptionMode)
    if (boxNumber) params.set('box_number', boxNumber)
    if (stockFilter !== 'all') params.set('stock_filter', stockFilter)
    if (onlyNullSublocation) params.set('only_null_sublocation', '1')
    if (onlySaleUnitGtOne) params.set('only_sale_unit_gt_one', '1')
    if (reviewStatus) params.set('review_status', reviewStatus)
    return api.get<LabelSearchResult>(`${BASE}/products/search?${params}`)
  },

  searchBoxes: (tenantId: string, storeId: string, q = '', startsWith = '') => {
    const params = scope(tenantId, storeId)
    if (q) params.set('q', q)
    if (startsWith) params.set('starts_with', startsWith)
    return api.get<BoxSearchResult>(`${BASE}/boxes/search?${params}`)
  },

  getBoxProducts: (tenantId: string, storeId: string, boxNumber: string) => {
    const params = scope(tenantId, storeId)
    params.set('box_number', boxNumber)
    return api.get<BoxProductResult>(`${BASE}/boxes/products?${params}`)
  },

  getProductBatches: (tenantId: string, storeId: string, productCode: string) => {
    const params = scope(tenantId, storeId)
    params.set('product_code', productCode)
    return api.get<ProductBatchResult>(`${BASE}/products/batches?${params}`)
  },

  updateReview: (tenantId: string, storeId: string, productCode: string, body: LabelReviewUpdateRequest) =>
    api.put(`${BASE}/products/${encodeURIComponent(productCode)}/review?${scope(tenantId, storeId)}`, body),

  /** One bulk backend call — never one request per product (spec §10). */
  bulkReview: (tenantId: string, storeId: string, productCodes: string[], includeLabel: IncludeLabel) =>
    api.put(`${BASE}/products/bulk-review?${scope(tenantId, storeId)}`, {
      product_codes: productCodes,
      include_label: includeLabel,
    }),

  /** Reviewer corrects the unit; auto-saved. old_unit_description is preserved server-side. */
  correctUnit: (tenantId: string, storeId: string, productCode: string, unitDescription: string, currentUnit?: string) =>
    api.put(`${BASE}/products/${encodeURIComponent(productCode)}/unit?${scope(tenantId, storeId)}`, {
      unit_description: unitDescription,
      current_unit: currentUnit,
    }),

  assignSublocation: (tenantId: string, storeId: string, productCode: string, sublocation: string) =>
    api.put(`${BASE}/products/${encodeURIComponent(productCode)}/sublocation?${scope(tenantId, storeId)}`, {
      sublocation,
    }),

  /** Super-admin manual box override; auto-saved. Bypasses the standard-box/
   * SYP assignment engine for one product. old location is preserved server-side. */
  correctLocation: (tenantId: string, storeId: string, productCode: string, location: string, currentLocation?: string) =>
    api.put(`${BASE}/products/${encodeURIComponent(productCode)}/location?${scope(tenantId, storeId)}`, {
      location,
      current_location: currentLocation,
    }),

  getProductTrend: (tenantId: string, storeId: string, productCode: string) =>
    api.get<LabelTrendResult>(`${BASE}/products/${encodeURIComponent(productCode)}/trend?${scope(tenantId, storeId)}`),

  getProductPurchases: (tenantId: string, storeId: string, productCode: string) =>
    api.get<LabelPurchaseResult>(`${BASE}/products/${encodeURIComponent(productCode)}/purchases?${scope(tenantId, storeId)}`),

  getProductSales: (tenantId: string, storeId: string, productCode: string) =>
    api.get<LabelSaleResult>(`${BASE}/products/${encodeURIComponent(productCode)}/sales?${scope(tenantId, storeId)}`),

  /** Compute (but never commit) the box plan — the UI previews before the operator confirms (spec §18). */
  previewAssignment: (tenantId: string, storeId: string, body: LabelAssignRequest) =>
    api.post<LabelAssignResult>(`${BASE}/assignments/preview?${scope(tenantId, storeId)}`, body),

  /** Commit the plan transactionally (super-admin only). */
  commitAssignment: (tenantId: string, storeId: string, body: LabelAssignRequest) =>
    api.post<LabelAssignResult>(`${BASE}/assignments/commit?${scope(tenantId, storeId)}`, body),

  getLabelQueue: (tenantId: string, storeId: string) =>
    api.get<LabelQueueResult>(`${BASE}/label-queue?${scope(tenantId, storeId)}`),

  markLabelsPrinted: (tenantId: string, storeId: string, productCodes: string[]) =>
    api.post(`${BASE}/label-queue/mark-printed?${scope(tenantId, storeId)}`, { product_codes: productCodes }),
}
