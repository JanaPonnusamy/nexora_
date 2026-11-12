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

export interface QuickStockCore {
  batches: QuickStockBatchRow[]
  purchases: QuickStockPurchaseRow[]
  sales: QuickStockSalesRow[]
  movement: unknown[]
}
