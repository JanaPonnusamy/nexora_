import { api } from './apiClient'
import type {
  AvailabilityRow,
  BatchRow,
  BillItemRow,
  CrossStoreMatchResult,
  CustomerBillRow,
  MovementRow,
  ProductDetails,
  PurchaseBillRow,
  PurchaseRow,
  RepeatPurchaseRow,
  SalesBillRow,
  SalesRow,
  StockSearchResult,
} from '../types/stock'

const BASE = '/api/stock-availability'

function qs(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== '') {
      search.set(key, String(value))
    }
  })
  const str = search.toString()
  return str ? `?${str}` : ''
}

export const stockService = {
  // ----- Search -------------------------------------------------------------
  searchProducts: (tenantId: string, q: string, onlyStock: boolean) =>
    api.get<StockSearchResult>(
      `${BASE}/products/search${qs({ tenant_id: tenantId, q, only_stock: onlyStock ? 1 : 0 })}`,
    ),
  searchBatches: (tenantId: string, batch: string, mrp: string, product: string) =>
    api.get<StockSearchResult>(
      `${BASE}/batches/search${qs({ tenant_id: tenantId, batch, mrp, product })}`,
    ),
  syncSelection: (
    tenantId: string,
    sourceStoreId: string,
    sourceProductCode: string,
    sourceProductName: string | null,
    targetStoreIds: string[],
  ) =>
    api.post<CrossStoreMatchResult>(`${BASE}/products/sync-selection`, {
      tenant_id: tenantId,
      source_store_id: sourceStoreId,
      source_product_code: sourceProductCode,
      source_product_name: sourceProductName,
      target_store_ids: targetStoreIds,
    }),

  // ----- Detail panels (active product context) -----------------------------
  productDetails: (tenantId: string, storeId: string, product: string) =>
    api.get<ProductDetails | null>(
      `${BASE}/products/details${qs({ tenant_id: tenantId, store_id: storeId, product })}`,
    ),
  batchDetails: (tenantId: string, storeId: string, product: string) =>
    api.get<BatchRow[]>(
      `${BASE}/products/batches${qs({ tenant_id: tenantId, store_id: storeId, product })}`,
    ),
  purchaseHistory: (tenantId: string, storeId: string, product: string) =>
    api.get<PurchaseRow[]>(
      `${BASE}/products/purchases${qs({ tenant_id: tenantId, store_id: storeId, product })}`,
    ),
  salesHistory: (tenantId: string, storeId: string, product: string) =>
    api.get<SalesRow[]>(
      `${BASE}/products/sales${qs({ tenant_id: tenantId, store_id: storeId, product })}`,
    ),
  billItems: (tenantId: string, storeId: string, billNo: string, billDate: string) =>
    api.get<BillItemRow[]>(
      `${BASE}/products/bill${qs({ tenant_id: tenantId, store_id: storeId, bill_no: billNo, bill_date: billDate })}`,
    ),
  monthlyMovement: (tenantId: string, storeId: string, product: string, months = 4) =>
    api.get<MovementRow[]>(
      `${BASE}/products/movement${qs({ tenant_id: tenantId, store_id: storeId, product, months })}`,
    ),

  // ----- Bill Drawer (Purchase Manager detail panel) ------------------------
  purchaseBill: (tenantId: string, storeId: string, grnNo: string, grnDate?: string | null) =>
    api.get<PurchaseBillRow[]>(
      `${BASE}/bills/purchase${qs({ tenant_id: tenantId, store_id: storeId, grn_no: grnNo, grn_date: grnDate ?? undefined })}`,
    ),
  salesBill: (tenantId: string, storeId: string, billNo: string, billDate?: string | null) =>
    api.get<SalesBillRow[]>(
      `${BASE}/bills/sale${qs({ tenant_id: tenantId, store_id: storeId, bill_no: billNo, bill_date: billDate ?? undefined })}`,
    ),
  setSalesBillIgnoreOrder: (payload: {
    tenant_id: string
    store_id: string
    bill_no: string
    bill_date: string
    product_code: string
    batch?: string | null
    dont_consider_in_order: boolean
  }) =>
    api.put<{ updated: number; dont_consider_in_order: boolean }>(`${BASE}/bills/sale/ignore-order`, payload),
  availability: (tenantId: string, storeId: string, product: string) =>
    api.get<AvailabilityRow[]>(
      `${BASE}/products/availability${qs({ tenant_id: tenantId, store_id: storeId, product })}`,
    ),
  customerHistory: (tenantId: string, storeId: string, customerCode: string) =>
    api.get<CustomerBillRow[]>(
      `${BASE}/customers/history${qs({ tenant_id: tenantId, store_id: storeId, customer_code: customerCode })}`,
    ),
  repeatPurchase: (tenantId: string, storeId: string, product: string) =>
    api.get<RepeatPurchaseRow[]>(
      `${BASE}/products/repeat${qs({ tenant_id: tenantId, store_id: storeId, product })}`,
    ),
}
