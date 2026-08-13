/* Types for the Label Exporter module. */

/* ---------- Product search ---------- */

export interface LabelSearchRow {
  product_code: string
  product_name: string
  unit_description: string | null
  box_number: string | null
  mrp: number
  total_stock: number
  sale_days: number | null
  purchase_days: number | null
}

export interface LabelSearchResult {
  rows: LabelSearchRow[]
  unit_descriptions: string[]
  last_box_for_letter: string | null
}

/* ---------- Box search ---------- */

export interface LabelBoxRow {
  box_number: string
  product_count: number
  total_stock: number
  best_sale_days: number | null
  best_purchase_days: number | null
}

export interface BoxSearchResult {
  boxes: LabelBoxRow[]
}

/* ---------- Box products ---------- */

export interface LabelBoxProductRow {
  product_code: string
  product_name: string
  unit_description: string | null
  mrp: number
  total_stock: number
  sale_days: number | null
  purchase_days: number | null
}

export interface BoxProductResult {
  rows: LabelBoxProductRow[]
}

/* ---------- Batch detail ---------- */

export interface LabelBatchRow {
  product_code: string
  batch_code: string
  stock: number
  expiry_date: string | null
  mrp: number
  sale_days: number | null
  purchase_days: number | null
  is_expired: boolean
}

export interface ProductBatchResult {
  rows: LabelBatchRow[]
}
