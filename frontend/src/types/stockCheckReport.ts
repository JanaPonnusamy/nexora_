export interface StockCheckRow {
  product_code: string | null
  sublocation: string | null
  product_name: string | null
  supplier_code: string | null
  supplier_name: string | null
  unit_description: string | null
  total_stock: number
  batch_stock: number
  expiry_date: string | null
  mrp: number
  sale_unit: string | null
  batch_code: string | null
  purchase_days: number | null
  sale_days: number | null
}

export interface StockCheckResult {
  rows: StockCheckRow[]
}

export interface StockCheckSupplierOption {
  supplier_code: string
  supplier_name: string | null
}

export interface StockCheckFilters {
  sublocationFrom: string
  sublocationTo: string
  productCodeFrom: string
  productCodeTo: string
  productName: string
  supplierCode: string
  unitDescription: string
  batchCode: string
  expiryFrom: string
  expiryTo: string
  minStock: string
  maxStock: string
  includeZeroStock: boolean
  includeNegativeStock: boolean
}

export const EMPTY_STOCK_CHECK_FILTERS: StockCheckFilters = {
  sublocationFrom: '',
  sublocationTo: '',
  productCodeFrom: '',
  productCodeTo: '',
  productName: '',
  supplierCode: '',
  unitDescription: '',
  batchCode: '',
  expiryFrom: '',
  expiryTo: '',
  minStock: '',
  maxStock: '',
  includeZeroStock: false,
  includeNegativeStock: false,
}
