export interface LabelSearchRow {
  product_code: string | null
  product_name: string | null
  unit_description: string | null
  sale_unit: number
  mrp: number
  total_stock: number
  current_sublocation: string | null
  purchase_days: number | null
  sale_days: number | null
  batch_stock: number
}

export interface LabelSearchResult {
  rows: LabelSearchRow[]
  last_box_for_letter: string | null
  unit_descriptions: string[]
}

export interface LabelBoxRow {
  box_number: string
  product_count: number
  total_stock: number
  best_sale_days: number | null
  best_purchase_days: number | null
}

export interface LabelBoxSearchResult {
  boxes: LabelBoxRow[]
}

export interface LabelBoxProductRow {
  product_code: string | null
  product_name: string | null
  total_stock: number
  sale_days: number | null
  purchase_days: number | null
  unit_description: string | null
  sale_unit: number
  mrp: number
}

export interface LabelBoxProductResult {
  rows: LabelBoxProductRow[]
}

export interface LabelBatchRow {
  product_code: string | null
  batch_code: string | null
  stock: number
  expiry_date: string | null
  mrp: number
  purchase_days: number | null
  sale_days: number | null
  is_expired: boolean
}

export interface LabelBatchResult {
  rows: LabelBatchRow[]
}
