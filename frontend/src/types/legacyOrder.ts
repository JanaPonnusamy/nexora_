/** Types for the Legacy Order console (old OrderNMC database). */

export interface LegacyStore {
  store_code: string
  store_name: string
  server_name: string
  database: string
  is_active: boolean
  last_sync_time: string | null
  last_sync_status: string | null
}

export interface LegacyTable {
  source: string
  destination: string
}

export type JobKind = 'sync' | 'order'
export type JobStatus = 'running' | 'completed' | 'failed'

export interface JobLogEntry {
  at: string
  message: string
}

export interface SyncTableResult {
  table: string
  destination: string
  rows: number
  status: 'ok' | 'partial' | 'error'
  error: string | null
}

export interface OrderHeaderResult {
  order_id: number
  order_no: number
  last_grn: string
  last_sale_bill_no: string
}

export interface LegacyJob {
  job_id: string
  kind: JobKind
  store_name: string
  status: JobStatus
  step: number
  total_steps: number
  message: string
  log: JobLogEntry[]
  result: {
    tables?: SyncTableResult[]
    rows?: number
    odata?: string
    header?: OrderHeaderResult | null
  } | null
  error: string | null
  started_at: string
  finished_at: string | null
}

export interface OrderRow {
  OrderId: number
  ProductCode: number
  ProductName: string
  TotalStock: number
  SaleUnit: number
  SLSQty: number
  MinQty: number
  MaxQty: number
  OrderQty: number
  OrgOrderQty: number
  WantedType: string
  ProductTypeName: string
  Frequence: number
  MRP: number
  PurchasePrice: number
  UnitDescription: string
  SubLocation: string
  LastSaleDate: string | null
  LastReceivedDate: string | null
  WantedDate: string | null
  Status: number
  Remarks: string | null
}

/** 'local' reads OrderNMC's own synced copy; 'remote' hits the branch DB live. */
export type OrderMode = 'local' | 'remote'
