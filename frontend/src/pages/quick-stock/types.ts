export interface QuickStockProduct {
  product_code: string | null
  product_name: string | null
  sale_unit: string | null
  stock: number
  mrp: number
}

export interface QuickStockBranch {
  store_id: string
  store_code: string | null
  store_name: string | null
  products: QuickStockProduct[]
}

export interface QuickStockSearchResult {
  stores: QuickStockBranch[]
}

export interface QuickStockTenant {
  tenant_id: string
  tenant_name: string
}

export interface QuickStockStoreShell {
  store_id: string
  store_code: string | null
  store_name: string | null
}

export interface QuickStockBatchRow {
  batch_no: string | null
  stock: number | null
  expiry_date: string | null
  age: string | null
  ptr: number | null
  mrp: number | null
}

export interface QuickStockPurchaseRow {
  grn_no: string | null
  date: string | null
  qty: number | null
  free: number | null
  dis: number | null
  cost: number | null
  ptr: number | null
  mrp: number | null
  supplier?: string | null
}

export interface QuickStockSalesRow {
  date: string | null
  bill_no: string | null
  customer: string | null
  qty: number | null
  mrp: number | null
  discount: number | null
}

export interface QuickStockMovementRow {
  period: string | null
  pur: number | null
  sal: number | null
  tin: number | null
  tout: number | null
  adj: number | null
  stk: number | null
}

export interface QuickStockCore {
  batches: QuickStockBatchRow[]
  purchases: QuickStockPurchaseRow[]
  sales: QuickStockSalesRow[]
  movement: QuickStockMovementRow[]
}

export interface QuickStockCoreBulkItem {
  store_id: string
  product_code: string
  batches: QuickStockBatchRow[]
  purchases: QuickStockPurchaseRow[]
  sales: QuickStockSalesRow[]
  movement: QuickStockMovementRow[]
}

export interface QuickStockCoreBulkResult {
  items: QuickStockCoreBulkItem[]
}

export interface QuickStockBillItem {
  line_no: number | null
  salesman: string | null
  product_code: string | null
  product_name: string | null
  sale_unit: string | null
  qty: number | null
  mrp: number | null
  discount_pct: number | null
  amount: number | null
}

export interface QuickStockGrnItem {
  grn_no: string | null
  invoice_series: string | null
  bill_date: string | null
  party_type: 'transfer' | 'supplier' | null
  supplier: string | null
  source_store_name: string | null
  supplier_code: string | null
  product_name: string | null
  batch: string | null
  expiry: string | null
  qty: number | null
  free: number | null
  ptr: number | null
  mrp: number | null
  tax: number | null
  discount: number | null
  margin: number | null
}

export type QuickStockCrossStoreMatchType =
  | 'EXACT_SUPPLIER_MATCH'
  | 'EXACT_NORMALIZED_NAME'
  | 'STRONG_ATTRIBUTE_MATCH'
  | 'RELEVANT_FUZZY_MATCH'
  | 'NO_MATCH'

export interface QuickStockCrossStoreMatch {
  store_id: string
  match_type: QuickStockCrossStoreMatchType
  score: number
  product: { product_code: string; product_name: string | null; mrp: number | null } | null
}
