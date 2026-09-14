export interface NmwSalesBill {
  bill_no: string | null
  bill_number: number | null
  bill_date: string | null
  bill_time: string | null
  issued_date: string | null
  bill_amount: number
  total_items: number | null
  total_qty: number
  customer_code: string | null
  customer_name: string | null
  is_transfer: number
  bill_type: string
  is_cancelled: number
  dest_store_id: string | null
  dest_store_code: string | null
  dest_store_name: string | null
  status: 'pending' | 'approved'
  is_shown: number
  approved_by: string | null
  approved_at: string | null
  purchase_status: PurchaseStatus
  purchase_entry_no: string | null
}

export interface NmwSalesBillList {
  bills: NmwSalesBill[]
  can_approve: boolean
  scope: 'store' | 'all'
  purchase_status_error: string | null
}

export interface NmwSalesBillItem {
  product_code: string | null
  product_name: string | null
  batch_no: string | null
  expiry_date: string | null
  qty: number
  free_qty: number
  mrp: number
  rate: number
  discount_percentage: number
  amount: number
  packing: string | null
  sublocation: string | null
}

export interface NmwSalesBillSummary {
  subtotal: number
  cgst: number
  sgst: number
  tax_total: number
  roundoff: number
  bill_amount: number
  is_transfer: number
}

export interface NmwStoreCustCode {
  store_id: string
  store_code: string | null
  store_name: string | null
  ho_cust_code: string | null
  ho_transfer_code: string | null
}

export interface BillKey {
  bill_date: string
  bill_no: string
}

export type PurchaseStatus = 'completed' | 'pending' | 'not_found' | 'error'

export type PurchaseStatusFilter = 'all' | PurchaseStatus

export interface NmwPendingProduct {
  product_code: string
  product_name: string | null
  required_qty: number
  received_qty: number
}

export interface NmwPurchaseEntry {
  purchase_status: PurchaseStatus
  matched_products: number
  total_products: number
  entry_no: string | null
  completing_grn: string | null
  entry_date: string | null
  pending_products: NmwPendingProduct[]
  match_basis: 'bill_number' | 'product_qty' | 'none' | null
  grn_amount: number | null
  dest_store_id: string | null
  dest_store_code: string | null
  dest_store_name: string | null
  reason: string | null
}
