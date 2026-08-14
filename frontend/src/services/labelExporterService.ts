import { api } from './apiClient'
import type {
  LabelBatchResult,
  LabelBoxProductResult,
  LabelBoxSearchResult,
  LabelSearchResult,
} from '../types/labelExporter'

export const labelExporterService = {
  searchProducts: (params: {
    tenantId: string
    storeId: string
    q: string
    startsWith: string
    unitDescription: string
    boxNumber: string
    stockFilter: string
    onlyNullSublocation: boolean
    onlySaleUnitGtOne: boolean
  }) =>
    api.get<LabelSearchResult>(
      `/api/label-exporter/products/search?tenant_id=${encodeURIComponent(params.tenantId)}` +
        `&store_id=${encodeURIComponent(params.storeId)}` +
        `&q=${encodeURIComponent(params.q)}` +
        `&starts_with=${encodeURIComponent(params.startsWith)}` +
        `&unit_description=${encodeURIComponent(params.unitDescription)}` +
        `&box_number=${encodeURIComponent(params.boxNumber)}` +
        `&stock_filter=${encodeURIComponent(params.stockFilter)}` +
        `&only_null_sublocation=${params.onlyNullSublocation ? 1 : 0}` +
        `&only_sale_unit_gt_one=${params.onlySaleUnitGtOne ? 1 : 0}`,
    ),
  searchBoxes: (tenantId: string, storeId: string, q: string, startsWith: string) =>
    api.get<LabelBoxSearchResult>(
      `/api/label-exporter/boxes/search?tenant_id=${encodeURIComponent(tenantId)}` +
        `&store_id=${encodeURIComponent(storeId)}` +
        `&q=${encodeURIComponent(q)}` +
        `&starts_with=${encodeURIComponent(startsWith)}`,
    ),
  getBoxProducts: (tenantId: string, storeId: string, boxNumber: string) =>
    api.get<LabelBoxProductResult>(
      `/api/label-exporter/boxes/products?tenant_id=${encodeURIComponent(tenantId)}` +
        `&store_id=${encodeURIComponent(storeId)}` +
        `&box_number=${encodeURIComponent(boxNumber)}`,
    ),
  getProductBatches: (tenantId: string, storeId: string, productCode: string) =>
    api.get<LabelBatchResult>(
      `/api/label-exporter/products/batches?tenant_id=${encodeURIComponent(tenantId)}` +
        `&store_id=${encodeURIComponent(storeId)}` +
        `&product_code=${encodeURIComponent(productCode)}`,
    ),
}
