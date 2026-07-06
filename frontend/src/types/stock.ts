// Stock Availability module — view-only stock lookup across a tenant's branches.

export interface StockProductRow {
  product_code: string | null
  product_name: string | null
  sale_unit: string | null
  stock: number
  mrp: number
  batch_no?: string | null
}

export interface BranchCard {
  store_id: string
  store_code: string | null
  store_name: string | null
  total_stock: number
  matching_count: number
  products: StockProductRow[]
}

export interface SearchSummary {
  total_stores: number
  total_products_found: number
  stores_with_stock: number
  total_stock_all_stores: number
}

export interface StockSearchResult {
  stores: BranchCard[]
  summary: SearchSummary
}

/** The active context every detail panel reloads from. */
export interface ProductContext {
  tenantId: string
  storeId: string
  storeName: string | null
  storeCode: string | null
  productCode: string
  productName: string | null
  stock: number
}

export interface ProductDetails {
  product_code: string | null
  product_name: string | null
  sale_unit: string | null
  mrp: number | null
  packing: number | null
  sublocation: string | null
  total_stock: number | null
  last_sale: string | null
  last_purchase: string | null
  /** Optional catalogue metadata — only present when the details API supplies
   *  it; the Purchase Decision header renders "—" otherwise. */
  manufacturer?: string | null
  category?: string | null
}

export interface BatchRow {
  batch_no: string | null
  stock: number | null
  expiry_date: string | null
  age: string | null
  ptr: number | null
  mrp: number | null
}

export interface PurchaseRow {
  grn_no: string | null
  date: string | null
  qty: number | null
  free: number | null
  dis: number | null
  cost: number | null
  ptr: number | null
  mrp: number | null
  /** Optional supplier label — the synced sync.PurchaseTrans currently carries
   *  no supplier, so this is only present if a future SP revision supplies it;
   *  the purchase grids render "—" otherwise. */
  supplier?: string | null
}

export interface SalesRow {
  date: string | null
  bill_no: string | null
  customer: string | null
  qty: number | null
  mrp: number | null
  discount: number | null
  /** Delivery Sales Rep (resolved from SaleInformation.DeliverySalesRep). */
  salesman?: string | null
}

/** One line of a Purchase Bill Drawer (all lines of a GRN). Header fields
 *  (grn_no/invoice_series/bill_date/supplier) repeat on every row. */
export interface PurchaseBillRow {
  grn_no: string | null
  invoice_series: string | null
  bill_date: string | null
  supplier: string | null
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

/** One line of a Sales Bill Drawer. Header fields repeat on every row. */
export interface SalesBillRow {
  bill_no: string | null
  bill_date: string | null
  customer: string | null
  customer_code: string | null
  salesman: string | null
  bill_value: number | null
  product_name: string | null
  batch: string | null
  qty: number | null
  mrp: number | null
  discount: number | null
  tax: number | null
}

/** Per-store availability of a product (drawer Availability tab). */
export interface AvailabilityRow {
  store_id: string | null
  store_code: string | null
  store_name: string | null
  stock: number | null
  is_current: number | null
  pending_qty: number | null
}

/** One of a customer's recent bills (drawer Customer History tab). */
export interface CustomerBillRow {
  bill_no: string | null
  date: string | null
  bill_value: number | null
  total_qty: number | null
}

/** A product usually bought together with the current one (Repeat Purchase). */
export interface RepeatPurchaseRow {
  product_name: string | null
  times_together: number | null
}

export interface BillItemRow {
  line_no: number | null
  salesman: string | null
  product_name: string | null
  sale_unit: string | null
  qty: number | null
  mrp: number | null
  discount_pct: number | null
  amount: number | null
}

export interface MovementRow {
  period: string | null
  pur: number | null
  sal: number | null
  tin: number | null
  tout: number | null
  adj: number | null
  stk: number | null
}
