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

export type JobKind = 'sync' | 'order' | 'stock'
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
    source_store?: string
    supplier_code?: string
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

/** One row of the Purchase-Manager-style order workspace grid. The common
 *  fields are a subset of OrderRow (so Review-All order_summary rows are
 *  structurally compatible); the stock-* fields are only present in the
 *  "Live Stock" supplier mode. */
export interface WorkspaceOrderRow {
  ProductCode: number
  ProductName: string
  OrderQty: number
  TotalStock: number
  SLSQty: number
  UnitDescription: string
  SaleUnit: number
  MRP: number
  WantedType: string | null
  Remarks: string | null
  PurchasePrice: number
  SubLocation: string | null
  Status: number
  ProductTypeName?: string
  MaxQty?: number
  // "Live Stock" mode only:
  S_Stock?: number
  Discount?: number | string | null
  MinQty?: number | null
  Sch?: number | null
  Free?: number | null
  SupplierProductName?: string | null
  SupplierProductCode?: string | null
  Rack?: string | null
}

/** Rows already assigned to a supplier (VB FetchSupplierOrderDetails). */
export interface AssignedOrderRow {
  ProductCode: number
  ProductName: string
  OrderQty: number
  SaleUnit: number
  MRP: number
  OrSupplier: string | null
  Remarks: string | null
  PurchasePrice: number
  TotalStock: number
  WantedType: string | null
  Status: number
}

export interface SupplierListItem {
  supplier_code: string
  supplier_name: string
}

export interface AssignResult {
  product_code: number
  status: number
  order_qty: number | null
  changed: boolean
}

/** Which supplier filter the workspace applies for a chosen supplier. */
export type SupplierOrderMode = 'history' | 'stock'

export interface QtyCheckRow {
  productcode: number
  productname: string
  orderqty: number
  totalstock: number
  saleunit: number
  unitdescription: string
  slsqty: number
  mrp: number
  lastreceiveddate: string | null
  lastsaledate: string | null
  maxsaleqty: number
  Transactiondate: string | null
  wantedtype: string | null
}

export interface QtyCheckUpdateResult {
  order_qty: number
  remarks: string
}

export interface PurchaseDetailRow {
  RStock: number | null
  FreeQty: number | null
  DIS: number | null
  ItemCost: number | null
  PTR: number | null
  MRP: number | null
  GRNDate: string | null
  SupplierName: string | null
}

export interface SalesDetailRow {
  TotalQuantity: number | null
  Bill_Time: string | null
  Salesmanname: string | null
  CUSTOMERNAME: string | null
  dis: number | null
  type: string | null
  mrp: number | null
  ptr: number | null
  Bnumber: string | null
}

export interface MonthlyStatRow {
  ProductCode: number
  MonthOfStatistics: string
  SaleQuantity: number
  StockInHand: number
  PurchaseQuantity: number
  AdjustmentQuantity: number
  TransferInQuantity: number
  TransferOutQuantity: number
}

export interface OrderHistoryRow {
  Productcode: number
  ProductName: string
  Orqty: number | null
  OrgOrderQty: number | null
  saleunit: number | null
  MRP: number | null
  remarks: string | null
  Wanteddate: string | null
  WantedType: string | null
  Orsupplier: string | null
}

export interface PreviousOrder {
  store_name: string
  order_id: number
  wanted_date: string
}

export interface PreviousOrderComparison {
  store_name: string
  order_id: number
  affected_rows: number
}

export interface PreviousOrderSupplier {
  supplier_code: string
  supplier_name: string
  product_count: number
}

export interface SupplierComparison extends PreviousOrderComparison {
  supplier_code: string
}

export interface SupplierComparisonProduct {
  CurrentProductCode: number | null
  CurrentProductName: string | null
  CurrentOrderQty: number | null
  CurrentWantedType: string | null
  PreviousProductCode: number
  PreviousProductName: string
  PreviousOrderedQty: number | null
  PreviousStock: number | null
  CurrentStock: number | null
  PreviousRemarks: string | null
  PreviousStatus: number | null
}

/** 'local' reads OrderNMC's own synced copy; 'remote' hits the branch DB live. */
export type OrderMode = 'local' | 'remote'

export interface LegacyDbHealth {
  database: string
  server: string | null
  reachable: boolean
  state: string | null
  access: string | null
  online: boolean
  message: string
}

export interface LegacyDbRecoveryStep {
  action: string
  ok: boolean
  detail: string
}

export interface LegacyDbRecovery {
  ok: boolean
  database: string
  before?: { state: string | null; access: string | null }
  after?: { state: string | null; access: string | null }
  connected?: boolean
  steps: LegacyDbRecoveryStep[]
  message: string
}
