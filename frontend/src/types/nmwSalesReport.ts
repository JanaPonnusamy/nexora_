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
  dest_store_id: string | null
  dest_store_code: string | null
  dest_store_name: string | null
  status: 'pending' | 'approved'
  approved_by: string | null
  approved_at: string | null
}

export interface NmwSalesBillList {
  bills: NmwSalesBill[]
  can_approve: boolean
  scope: 'store' | 'all'
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
}

export interface NmwStoreCustCode {
  store_id: string
  store_code: string | null
  store_name: string | null
  ho_cust_code: string | null
}

export interface BillKey {
  bill_date: string
  bill_no: string
}
