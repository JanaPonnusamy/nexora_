/** Types for the Legacy Order console (old OrderNMC database). */

export interface LegacyStore {
  store_code: string
  store_name: string
  server_name: string
  database: string
  is_active: boolean
  last_sync_time: string | null
  last_sync_status: string | null
  tenant_id?: string | null
  tenant_name?: string | null
  /** Name to show; two tenants can share it while store_name stays the unique key. */
  display_name?: string | null
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
  warning: string | null
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
  // true when this row's stock came from the NMW/Ho_code pseudo-supplier
  // (warehouse stock bridged via product_mapping), not a real supplier.
  is_warehouse_stock?: boolean
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
  ProductTypeName?: string
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
  producttypename: string | null
}

/** VB.NET's "Pending Order" screen: lines already reviewed (qtycheck = 1)
 *  but not yet assigned to a supplier (status = 0). */
export interface PendingOrderRow {
  productcode: number
  productname: string
  orderqty: number
  totalstock: number
  slsqty: number
  unitdescription: string
  saleunit: number
  mrp: number
  lastreceiveddate: string | null
  lastsaledate: string | null
  maxsaleqty: number
  Transactiondate: string | null
  wantedtype: string | null
}

export interface ResetPendingResult {
  assigned_marked: number
  remaining_reset: number
}

export type OrderWorkflowStatus =
  | 'DRAFT'
  | 'QTY_REVIEW'
  | 'SUPPLIER_ASSIGNMENT'
  | 'READY'
  | 'FINALIZED'

export interface OrderWorkflowSummary {
  store_name: string
  order_id: number | null
  status: OrderWorkflowStatus
  ready: boolean
  total_lines: number
  qty_pending: number
  qty_reviewed: number
  assigned_lines: number
  unassigned_lines: number
  closed_lines: number
  assigned_qty: number
  assigned_value: number
  supplier_count: number
  updated_at: string | null
  updated_by: string | null
  finalized_at: string | null
  note: string | null
}

export interface OrderWorkflowAuditEntry {
  AuditId: number
  OrderId: number
  ProductCode: number | null
  Action: string
  OldValue: string | null
  NewValue: string | null
  Actor: string | null
  CreatedAt: string
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

/** Monthly stock-movement row for a product (RetrieveDataForChartAsync port).
 *  `sales` is already NET of sales returns and `adjustment` is signed and
 *  already includes expiry returns -- ProductTrans is the POS's own rollup
 *  and its closing-stock identity reconciles without adding returns again.
 *  The `*_return`/`gross_sales`/`stock_adjustment` fields are breakdown-only,
 *  for the tooltip; they must never be added into `total_in`/`total_out`. */
export interface MonthlyStatRow {
  month: string
  purchase: number
  transfer_in: number
  sales: number
  transfer_out: number
  adjustment: number
  stock: number
  total_in: number
  total_out: number
  gross_sales: number
  sales_return: number
  expiry_return: number
  stock_adjustment: number
  purchase_return: number | null
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
  CurrentSLSQty: number | null
  CurrentLastSaleDate: string | null
  CurrentLastReceivedDate: string | null
  LastReceivedQty: number | null
  LastGRNDate: string | null
}

/** 'local' reads OrderNMC's own synced copy; 'remote' hits the branch DB live. */
export type OrderMode = 'local' | 'remote' | 'nexora'

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

/** Preview for the pending-supplier-assignment WARNING dialog (not a lock --
 *  see service.start_order_process). When count > 1, Process requires an
 *  admin to confirm Admin Override & Process; order_id/count are echoed
 *  back on startOrderProcess so the server can detect stale state. */
export interface QtyCheckConfirmation {
  order_id: number | null
  count: number
  sample: { product_code: number; product_name: string }[]
}

export interface RestorableOrderPreview {
  store_name: string
  order_id: number
  product_count: number
  backed_up_at: string | null
  suppliers: PreviousOrderSupplier[]
}

export interface RestoreResult {
  store_name: string
  source_order_id: number
  restored_count: number
  actor: string | null
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

/** ---- PM Order Entry: automated order submit (per store) ---- */

export type PmOrderType = 'REGULAR' | 'WH'

export interface PmOrderEntryJobLog {
  at: string
  message: string
}

export interface PmOrderEntryJob {
  job_id: string
  status: 'running' | 'completed' | 'failed'
  message: string
  error: string | null
  log: PmOrderEntryJobLog[]
}

export interface PmOrderEntryLatestOrder {
  order_id: number
  order_no: number | null
  status: OrderWorkflowStatus
  qty_pending: number
  unassigned_lines: number
}

export interface PmOrderEntryHeader {
  order_datetime: string | null
  last_sale_bill_no: string | null
  last_grn: string | null
}

/** GET .../order-entry */
export interface PmOrderEntryState {
  store_name: string
  latest_order: PmOrderEntryLatestOrder | null
  blocked: boolean
  header: PmOrderEntryHeader | null
  gap_review?: GapReviewStatus | null
  job: PmOrderEntryJob | null
}

/** Order Entry step 1: the PM's review of the current order's gap. */
export interface GapReviewStatus {
  required: boolean
  done: boolean
  order_id: number | null
  reviewed_at: string | null
  reviewed_by: string | null
  not_received?: number | null
  pending_count?: number | null
}

export type PmOrderQueueStatus = 'PENDING' | 'RUNNING' | 'DONE' | 'FAILED'

/** POST (queued) / GET .../order-entry/queue */
export interface PmOrderQueueRow {
  queue_id: number
  store_name: string
  last_bill: string
  last_grn: string
  order_type: PmOrderType
  confirmed: boolean
  status: PmOrderQueueStatus
  queued_at: string | null
  run_at: string | null
  started_at: string | null
  finished_at: string | null
  job_id: string | null
  error: string | null
}

/** POST .../order-entry when automation is off */
export interface PmOrderEntryImmediateResult {
  queued: false
  job_id: string
}

export type PmOrderEntrySubmitResult = PmOrderQueueRow & { queued: true } | PmOrderEntryImmediateResult

/** Plain "most recent N" rows for the PM's own verification grids -- see
 *  GET .../order-entry/recent. Deliberately unfiltered (no received-not-
 *  ordered exclusion), so row 0 of each always matches the Current Order
 *  card's Last bill / Last GRN watermark. */
export interface RecentGrnRow {
  grn_no: number
  grn_date: string | null
  supplier_code: string | null
  supplier_name: string | null
  item_count: number
  total_qty: number
  /** When this GRN reached central OrderNMC via sync -- a fallback only,
   *  used when grn_time is unavailable (rows synced before TransactionTime
   *  was added to the pipeline, or an agent-synced store whose remote
   *  source has no such column). */
  synced_at: string | null
  /** The branch's real GRN entry time (PurchaseTrans.TransactionTime).
   *  NULL for rows synced before this column existed and for agent-synced
   *  stores -- grndate itself has no time component at the source. */
  grn_time: string | null
}

export interface RecentSaleBillRow {
  bill_no: string | null
  bill_date: string | null
  salesman: string | null
  customer: string | null
  amount: number
}

export interface PmOrderEntryRecent {
  store_name: string
  grns: RecentGrnRow[]
  bills: RecentSaleBillRow[]
}

/** GET/PUT .../automation */
export interface OrderEntryAutomation {
  store_name: string
  automated_order_enabled: boolean
  production_mode: boolean
  min_delay_seconds: number
  max_delay_seconds: number
  updated_at: string | null
  updated_by: string | null
}

export type MessageType = 'ORDER_GENERATED' | 'STOCK_LIST' | 'TIME_LIST' | 'STOCK_READY' | 'ENTRY_READY'

export interface MessageTarget {
  name: string
  kind: 'group' | 'contact'
}

/** GET/PUT .../message-settings[/{message_type}] */
export interface MessageSetting {
  store_name: string
  message_type: MessageType
  enabled: boolean
  targets: MessageTarget[]
  updated_at: string | null
  updated_by: string | null
}

/** ---- Live Queries / Repair (db-monitor) ---- */

export interface DbMonitorRequest {
  session_id: number
  status: string
  command: string | null
  wait_type: string | null
  wait_time_ms: number | null
  blocking_session_id: number | null
  cpu_time_ms: number | null
  total_elapsed_ms: number | null
  reads: number | null
  writes: number | null
  logical_reads: number | null
  row_count: number | null
  start_time: string | null
  login_name: string | null
  host_name: string | null
  program_name: string | null
  database_name: string | null
  query_text: string | null
}

export interface DbMonitorSession {
  session_id: number
  status: string
  login_name: string | null
  host_name: string | null
  program_name: string | null
  database_name: string | null
  last_request_start_time: string | null
  last_request_end_time: string | null
  total_elapsed_ms: number | null
  blocking_session_id: number | null
  wait_type: string | null
}

export interface DbMonitorKillResult {
  session_id: number
  killed: true
}

/** Order Gap Review: a PM's reconciliation screen for the gap since the
 *  store's last placed order, which may span multiple days (e.g. reviewing
 *  Saturday's order on Monday). See GET/POST/DELETE .../gap-review*. */
export interface NotReceivedRow {
  product_code: number | null
  product_name: string | null
  ordered_qty: number
  order_date: string | null
  product_type?: string
  supplier_name?: string | null
  mrp?: number | null
  stock?: number | null
  sales_90?: number | null
  remarks?: string | null
}

export interface ReceivedNotOrderedRow {
  grn_no: number
  grn_date: string | null
  supplier_code: string | null
  supplier_name: string | null
  product_code: number | null
  product_name: string | null
  qty: number
  free_qty: number
  purchase_price: number
  mrp: number
  product_type: string
}

/** A PM-flagged "ordered but never arrived" line that carries forward as a
 *  reminder across reviews until a later GRN arrives or it is dismissed. */
export interface PendingOrderItem {
  id: number
  store_name: string
  product_code: number | null
  product_name: string | null
  order_id: number | null
  qty: number | null
  flagged_at: string | null
  flagged_by: string | null
  cleared_at: string | null
  note: string | null
}

/** GET .../gap-review */
export interface OrderGapReview {
  store_name: string
  order_id: number | null
  order_date: string | null
  not_received: NotReceivedRow[]
  received_not_ordered: ReceivedNotOrderedRow[]
  pending_items: PendingOrderItem[]
  review?: GapReviewStatus | null
}
