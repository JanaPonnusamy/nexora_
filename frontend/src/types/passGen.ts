/** Pass Gen — legacy 14-character store passcodes (generation only). */

export interface PassGenStore {
  store_id: string
  tenant_id: string
  store_code: string
  store_name: string | null
  /** Numeric code the passcode format needs (NMS = 6, …). Null = unmapped. */
  numeric_code: number | null
}

export interface PassGenRow {
  row_id: string
  /** Empty = every mapped store. */
  store_ids: string[]
  min_days: number
  max_days: number
  order_yes: number
  compare_last_order: number
}

export interface PassGenRequest {
  order_no: number
  target_date: string
  rows: PassGenRow[]
}

export interface PassGenResult {
  store_id: string
  store_code: string
  store_name: string | null
  numeric_code: number
  passcode: string
}

export interface PassGenRowResult {
  row_id: string
  results: PassGenResult[]
  /** Store codes left out because they have no numeric code yet. */
  skipped: string[]
}

export interface PassGenResponse {
  rows: PassGenRowResult[]
}
