import { useCallback, useRef, useState } from 'react'
import type { PurchaseRow, SalesRow } from '../../types/stock'
import type { SupplierRow, WorkspaceItem } from '../../types/procurement'
import type { BillTarget } from './BillDrawer'
import { stockService } from '../../services/stockService'
import { useStockResource } from '../stock/useStockResource'
import { MovementChart } from '../stock/MovementChart'
import { EmptyState } from '../common/EmptyState'
import { SupplierPicker } from './SupplierPicker'
import { money, num } from '../stock/format'
import { useMiniGridSettings, type MiniGridColumn } from './useMiniGridSettings'
import { MiniGridSettingsPanel } from './MiniGridSettingsPanel'
import '../stock/stock-ui.css'

/** dd-mm-yy — compact numeric date for the Purchase/Sales History mini
 *  tables' narrow Date column (the shared date() util's "09 Jul 25" is wider
 *  than these columns can spare; kept local rather than changed app-wide). */
function shortDate(value: string | null | undefined): string {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  const dd = String(d.getDate()).padStart(2, '0')
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const yy = String(d.getFullYear()).slice(-2)
  return `${dd}-${mm}-${yy}`
}

/** The item's current live (non-exported) assignment, if any — used to offer
 *  inline Change Supplier from the Review-All detail panel (§4), without
 *  requiring the buyer to switch to Supplier Purchasing mode. */
export interface AssignedSupplierInfo {
  assignmentId: string
  supplierCode: string
  supplierName: string | null
}

/** Which drawer tab a panel action opens. */
export type DrawerTab = 'info' | 'history' | 'decision'
/** History "View All" dialog target. */
export type ViewAllKind = 'purchase' | 'sales'

/** Real per-supplier offer facts (Supplier Live Stock only — sourced from
 *  procurement.supplier_stock's scheme/free/discount, not the still-unpopulated
 *  WorkspaceItem.offer field). Optional: absent in Review All / Supplier
 *  Purchasing, which have no such per-supplier data source. */
export interface OfferInfo {
  supplierName: string | null
  label: string
  discount?: number | null
}

/**
 * Right-hand Purchase Decision Panel. Fits entirely inside the viewport (the
 * page never scrolls because of it): the Product header, Sales Trend chart and
 * Supplier Recommendation stay pinned, while Purchase History and Sales History
 * scroll internally at a fixed height. Batch / Expiry / PTR / MRP detail
 * belongs to GRN, not the Purchase Manager, so it is intentionally absent here.
 */
export function DetailColumn({
  tenantId,
  item,
  loading = false,
  onOpenInfo,
  onOpenBill,
  onViewAll,
  assignedSupplier,
  onChangeSupplier,
  onRemoveAssignment,
  offerInfo,
  supplierRemarks,
}: {
  tenantId: string
  item: WorkspaceItem | null
  loading?: boolean
  onOpenInfo?: (item: WorkspaceItem, tab?: DrawerTab) => void
  /** Open the Purchase/Sales Bill Drawer for a clicked history row. */
  onOpenBill?: (target: BillTarget) => void
  /** Open the full History "View All" dialog (search / sort / export). */
  onViewAll?: (kind: ViewAllKind) => void
  /** The selected item's current supplier assignment, if any (§4 — lets Review
   *  All mode offer Change Supplier without switching to Supplier Purchasing). */
  assignedSupplier?: AssignedSupplierInfo | null
  onChangeSupplier?: (assignmentId: string, newSupplier: SupplierRow) => void
  /** Unassign the current supplier from this product (reverts to review/draft). */
  onRemoveAssignment?: () => void
  /** § OFFER SUPPORT — Supplier / Offer / Discount for the currently viewed
   *  supplier-stock row, when available. */
  offerInfo?: OfferInfo | null
  /** Free-text remarks entered against this product in Supplier Live Stock's
   *  Remarks column, when available (§ PRODUCT DETAILS). */
  supplierRemarks?: string | null
}) {
  const [viewMode, setViewMode] = useState<'summary' | 'history'>('summary')
  const [changingSupplier, setChangingSupplier] = useState(false)

  const storeId = item?.store_id ?? ''
  const productCode = item?.product_code ?? ''
  const productName = item?.product_name ?? null
  const hasProduct = Boolean(item && storeId && productCode)

  // Open a bill drawer for a history row (row carries the product context).
  const openPurchaseBill = (r: PurchaseRow) =>
    onOpenBill?.({ kind: 'purchase', storeId, billId: r.grn_no ?? '', billDate: r.date, productCode, productName })
  const openSalesBill = (r: SalesRow) =>
    onOpenBill?.({ kind: 'sales', storeId, billId: r.bill_no ?? '', billDate: r.date, productCode, productName })

  // Product-scoped stock resources (idle until a product is selected; each
  // reloads only when the product changes).
  const ctxKey = hasProduct ? `${tenantId}|${storeId}|${productCode}` : null

  const salesFetch = useCallback(
    () => stockService.salesHistory(tenantId, storeId, productCode),
    [tenantId, storeId, productCode],
  )
  const sales = useStockResource(salesFetch, ctxKey, 'sales')

  const purchasesFetch = useCallback(
    () => stockService.purchaseHistory(tenantId, storeId, productCode),
    [tenantId, storeId, productCode],
  )
  const purchases = useStockResource(purchasesFetch, ctxKey, 'purchases')

  const movementFetch = useCallback(
    () => stockService.monthlyMovement(tenantId, storeId, productCode, 4),
    [tenantId, storeId, productCode],
  )
  const movement = useStockResource(movementFetch, ctxKey, 'movement')

  // Store Count / cross-store stock — reuses the same Availability data the
  // Bill Drawer's own tab already fetches (§ PRODUCT DETAILS), just surfaced
  // inline here so the buyer never has to open a bill to see it.
  const availabilityFetch = useCallback(
    () => stockService.availability(tenantId, storeId, productCode),
    [tenantId, storeId, productCode],
  )
  const availability = useStockResource(availabilityFetch, ctxKey, 'availability')

  const purchaseGrid = useMiniGridSettings('pm.purchaseHistory', PURCHASE_COLUMNS, DEFAULT_MINITABLE_PADDING)
  const salesGrid = useMiniGridSettings('pm.salesHistory', SALES_COLUMNS, DEFAULT_MINITABLE_PADDING)
  const [gridSettingsOpen, setGridSettingsOpen] = useState(false)
  const panelRef = useRef<HTMLDivElement>(null)

  if (!item || !hasProduct) {
    return (
      <div className="pm-dpanel pm-dpanel--empty">
        <EmptyState
          icon={loading ? 'bi-hourglass-split' : 'bi-hand-index'}
          title={loading ? 'Loading product details...' : 'Select a product'}
          description={
            loading
              ? 'The current workspace context is loading.'
              : 'Choose a row on the left to see the sales trend, supplier recommendation, recent purchases and sales.'
          }
        />
      </div>
    )
  }

  const openInfo = onOpenInfo ? (tab: DrawerTab) => onOpenInfo(item, tab) : undefined

  return (
    <div className="pm-dpanel pm-dpanel--fit" key={item.order_item_id} ref={panelRef}>
      {/* Product header + view-mode switch (no Mfr/Category/Location clutter) */}
      <header className="pm-dhead">
        <div className="min-w-0">
          {/* Name + code/unit/pack/stores/last-rate on ONE line (baseline-
              aligned, name bold + meta muted) instead of two stacked rows —
              and the whole header is a row now (see .pm-dhead), so Summary/
              History/Info sit beside this instead of claiming their own row
              below it. */}
          <div className="pm-dhead__titleline">
            <span className="pm-dhead__name">{item.product_name ?? item.product_code ?? '—'}</span>
            {/* Store Count comes from Availability (same source the Bill
                Drawer's own tab uses); Last rate is the top Purchase History row. */}
            <span className="pm-dhead__meta pm-dhead__meta--compact">
              {[
                item.product_code,
                item.unit_description,
                item.pack ? `Pack ${item.pack}` : null,
                availability.isLoading
                  ? 'Stores …'
                  : availability.data
                    ? `${availability.data.filter((a) => (a.stock ?? 0) > 0).length}/${availability.data.length} Stores`
                    : null,
                purchases.isLoading
                  ? 'Last …'
                  : purchases.data && purchases.data.length > 0
                    ? `Last ${money(purchases.data[0].ptr)}`
                    : null,
              ].filter(Boolean).join(' • ')}
            </span>
          </div>
          {/* § OFFER SUPPORT — Supplier / Offer / Discount, when the caller has
              real per-supplier scheme data (Supplier Live Stock only). No
              "Validity" line: supplier_stock carries no expiry/validity date,
              so nothing is shown rather than fabricated. */}
          {offerInfo && (
            <div className="pm-dhead__meta pm-dhead__offer">
              <span><b>Supplier</b>{offerInfo.supplierName ?? '—'}</span>
              <span><b>Offer</b><span className="pm-offer">{offerInfo.label}</span></span>
              {offerInfo.discount != null && offerInfo.discount > 0 && (
                <span><b>Discount</b>{offerInfo.discount}%</span>
              )}
            </div>
          )}
          {supplierRemarks && (
            <div className="pm-dhead__meta"><span><b>Remarks</b>{supplierRemarks}</span></div>
          )}
          {/* Inline Change Supplier (§4) — reassignment reachable from Review
              All mode too, not only Supplier Purchasing's own review panel. */}
          {assignedSupplier && onChangeSupplier && (
            changingSupplier ? (
              <div className="pm-dhead__changesup">
                <SupplierPicker
                  tenantId={tenantId}
                  storeId={item.store_id ?? undefined}
                  value={null}
                  onPick={(s) => {
                    if (s) onChangeSupplier(assignedSupplier.assignmentId, s)
                    setChangingSupplier(false)
                  }}
                  onReturnToGrid={() => setChangingSupplier(false)}
                />
                <button className="pm-linkbtn pm-linkbtn--sm" onClick={() => setChangingSupplier(false)}>Cancel</button>
              </div>
            ) : (
              <div className="pm-dhead__assigned">
                <i className="bi bi-truck" aria-hidden="true" />
                Assigned to <b>{assignedSupplier.supplierName ?? assignedSupplier.supplierCode}</b>
                <button className="pm-linkbtn pm-linkbtn--sm" onClick={() => setChangingSupplier(true)}>Change</button>
                {onRemoveAssignment && (
                  <button className="pm-linkbtn pm-linkbtn--sm pm-linkbtn--danger" onClick={onRemoveAssignment}>Remove</button>
                )}
              </div>
            )
          )}
        </div>
        <div className="pm-dhead__actions">
          <div className="pm-vswitch" role="tablist" aria-label="Detail view mode">
            {(['summary', 'history'] as const).map((v) => (
              <button
                key={v}
                role="tab"
                aria-selected={viewMode === v}
                className={`pm-vswitch__btn${viewMode === v ? ' pm-vswitch__btn--on' : ''}`}
                onClick={() => setViewMode(v)}
              >
                {v === 'summary' ? 'Summary' : 'History'}
              </button>
            ))}
          </div>
          {openInfo && (
            <button className="pm-btn pm-btn--ghost pm-btn--sm" onClick={() => openInfo('info')} title="Product information">
              <i className="bi bi-info-circle" /> Info
            </button>
          )}
          <button
            className="pm-btn pm-btn--ghost pm-btn--sm"
            onClick={() => setGridSettingsOpen((v) => !v)}
            title="Purchase/Sales History grid settings"
            aria-expanded={gridSettingsOpen}
          >
            <i className="bi bi-gear" />
          </button>
        </div>
      </header>

      {gridSettingsOpen && panelRef.current && (
        <MiniGridSettingsPanel
          anchorRect={panelRef.current.getBoundingClientRect()}
          onClose={() => setGridSettingsOpen(false)}
          sections={[
            {
              title: 'Purchase History columns',
              columns: PURCHASE_COLUMNS,
              order: purchaseGrid.order,
              widths: purchaseGrid.widths,
              padding: purchaseGrid.padding,
              onMove: purchaseGrid.moveColumn,
              onWidth: purchaseGrid.setColumnWidth,
              onPadding: purchaseGrid.setPadding,
              onReset: purchaseGrid.reset,
            },
            {
              title: 'Sales History columns',
              columns: SALES_COLUMNS,
              order: salesGrid.order,
              widths: salesGrid.widths,
              padding: salesGrid.padding,
              onMove: salesGrid.moveColumn,
              onWidth: salesGrid.setColumnWidth,
              onPadding: salesGrid.setPadding,
              onReset: salesGrid.reset,
            },
          ]}
        />
      )}

      {viewMode === 'history' ? (
        <HistoryView
          purchases={purchases} sales={sales} onOpenPurchase={openPurchaseBill} onOpenSales={openSalesBill}
          purchaseGrid={purchaseGrid} salesGrid={salesGrid}
        />
      ) : (
        <>
          {/* Sales Trend, Purchase History, Sales History — three equal-height
              rows (each flex:1 1 0, see .pm-dsec--trend/.pm-dsec--scroll),
              full panel width apiece so neither history table needs to
              truncate/scroll horizontally to show its columns. */}
          <section className="pm-dsec pm-dsec--trend">
            <div className="pm-dsec__title"><i className="bi bi-graph-up" /> Sales Trend</div>
            <div className="pm-chart-wrap">
              {movement.isLoading ? (
                <div className="pm-dsec__hint">Loading movement…</div>
              ) : !movement.data || movement.data.length === 0 ? (
                <div className="pm-dsec__hint">No movement in the last 4 months.</div>
              ) : (
                <MovementChart rows={movement.data} flat />
              )}
            </div>
          </section>

          <section className={`pm-dsec pm-dsec--pur pm-dsec--scroll${!purchases.isLoading && (purchases.data?.length ?? 0) === 0 ? ' pm-dsec--empty' : ''}`}>
            <div className="pm-dsec__title">
              <i className="bi bi-truck" /> Purchase History
              {onViewAll && (
                <button className="pm-linkbtn pm-dsec__titlebtn" onClick={() => onViewAll('purchase')}>
                  View All
                </button>
              )}
            </div>
            <PurchaseMiniTable purchases={purchases} onRowClick={openPurchaseBill} order={purchaseGrid.order} widths={purchaseGrid.widths} padding={purchaseGrid.padding} />
          </section>

          <section className={`pm-dsec pm-dsec--sales pm-dsec--scroll${!sales.isLoading && (sales.data?.length ?? 0) === 0 ? ' pm-dsec--empty' : ''}`}>
            <div className="pm-dsec__title">
              <i className="bi bi-cart-check" /> Sales History
              {onViewAll && (
                <button className="pm-linkbtn pm-dsec__titlebtn" onClick={() => onViewAll('sales')}>
                  View All
                </button>
              )}
            </div>
            <SalesMiniTable sales={sales} onRowClick={openSalesBill} order={salesGrid.order} widths={salesGrid.widths} padding={salesGrid.padding} />
          </section>
        </>
      )}
    </div>
  )
}

/* ---- History view (full purchase + sales tables) -------------------------- */

type Res<T> = { data: T | null; isLoading: boolean }

function HistoryView({
  purchases,
  sales,
  onOpenPurchase,
  onOpenSales,
  purchaseGrid,
  salesGrid,
}: {
  purchases: Res<PurchaseRow[]>
  sales: Res<SalesRow[]>
  onOpenPurchase: (r: PurchaseRow) => void
  onOpenSales: (r: SalesRow) => void
  purchaseGrid: { order: string[]; widths: Record<string, number>; padding: number }
  salesGrid: { order: string[]; widths: Record<string, number>; padding: number }
}) {
  return (
    <>
      <section className="pm-dsec pm-dsec--pur pm-dsec--scroll pm-dsec--grow">
        <div className="pm-dsec__title"><i className="bi bi-truck" /> Purchase History</div>
        <PurchaseMiniTable purchases={purchases} limit={100} onRowClick={onOpenPurchase} order={purchaseGrid.order} widths={purchaseGrid.widths} padding={purchaseGrid.padding} />
      </section>
      <section className="pm-dsec pm-dsec--sales pm-dsec--scroll pm-dsec--grow">
        <div className="pm-dsec__title"><i className="bi bi-cart-check" /> Sales History</div>
        <SalesMiniTable sales={sales} limit={100} onRowClick={onOpenSales} order={salesGrid.order} widths={salesGrid.widths} padding={salesGrid.padding} />
      </section>
    </>
  )
}

/* ---- Compact grids -------------------------------------------------------- */

/** Default widths (px) — the floor from the earlier truncation fix, verified
 *  live via DevTools to be genuinely wide enough for every header/value at
 *  this panel's real width. User overrides (via the ⚙ settings panel) start
 *  from these. */
export const PURCHASE_COLUMNS: MiniGridColumn[] = [
  { id: 'qty', label: 'Qty', width: 38 },
  { id: 'free', label: 'Free', width: 38 },
  { id: 'dis', label: 'Dis%', width: 42 },
  { id: 'date', label: 'Date', width: 60 },
  { id: 'cost', label: 'Cost', width: 58 },
  { id: 'ptr', label: 'PTR', width: 58 },
  { id: 'mrp', label: 'MRP', width: 58 },
  { id: 'sup', label: 'Sup', width: 110 },
]
export const SALES_COLUMNS: MiniGridColumn[] = [
  { id: 'qty', label: 'Qty', width: 38 },
  { id: 'bill', label: 'Bill', width: 70 },
  { id: 'date', label: 'Date', width: 60 },
  { id: 'cust', label: 'Cust', width: 110 },
  { id: 'dis', label: 'Dis%', width: 42 },
  { id: 'rep', label: 'Rep', width: 80 },
]
export const DEFAULT_MINITABLE_PADDING = 3

function PurchaseMiniTable({
  purchases, limit = 50, onRowClick, order, widths, padding,
}: {
  purchases: Res<PurchaseRow[]>; limit?: number; onRowClick?: (r: PurchaseRow) => void
  order: string[]; widths: Record<string, number>; padding: number
}) {
  if (purchases.isLoading) return <div className="pm-dsec__hint">Loading purchases…</div>
  const rows = purchases.data ?? []
  if (rows.length === 0) return <div className="pm-dsec__hint">No recent purchases.</div>

  const cell: Record<string, { th: React.ReactNode; num?: boolean; td: (r: PurchaseRow) => React.ReactNode }> = {
    qty: { th: 'Qty', num: true, td: (r) => num(r.qty) },
    free: {
      th: 'Free', num: true,
      td: (r) => num(r.free),
    },
    dis: { th: 'Dis%', num: true, td: (r) => (r.dis != null ? `${num(r.dis)}%` : '—') },
    date: { th: 'Date', td: (r) => <span className="sx-dim">{shortDate(r.date)}</span> },
    cost: { th: 'Cost', num: true, td: (r) => money(r.cost) },
    ptr: { th: 'PTR', num: true, td: (r) => money(r.ptr) },
    mrp: { th: 'MRP', num: true, td: (r) => money(r.mrp) },
    sup: { th: 'Sup', td: (r) => <span className="pm-mt__ellip">{r.supplier ?? '—'}</span> },
  }

  return (
    <div className="pm-minitable-wrap">
      <table className="pm-minitable pm-minitable--click pm-minitable--pur" style={{ '--pm-mt-pad': `${padding}px` } as React.CSSProperties}>
        {/* Real, readable px widths (user-adjustable via ⚙ settings) — this
            panel's width can't fit every column without truncation no
            matter how they're split, so the table takes its real
            (wider-than-container) width and scrolls horizontally instead
            (.pm-minitable-wrap has overflow-x:auto) rather than crushing
            text to force a no-scroll fit. */}
        <colgroup>
          {order.map((id) => <col key={id} style={{ width: `${widths[id] ?? 50}px` }} />)}
        </colgroup>
        <thead>
          <tr>
            {order.map((id) => <th key={id} className={cell[id]?.num ? 'sx-num' : undefined}>{cell[id]?.th}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, limit).map((r, i) => {
            const isFree = (r.free ?? 0) > 0
            return (
              <tr
                key={`${r.grn_no}-${i}`}
                className={isFree ? 'pm-mt__free' : undefined}
                onClick={() => onRowClick?.(r)}
                title={isFree ? `Open purchase bill · includes ${num(r.free)} free unit(s)` : 'Open purchase bill'}
              >
                {order.map((id) => <td key={id} className={cell[id]?.num ? 'sx-num' : undefined}>{cell[id]?.td(r)}</td>)}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function SalesMiniTable({
  sales, limit = 50, onRowClick, order, widths, padding,
}: {
  sales: Res<SalesRow[]>; limit?: number; onRowClick?: (r: SalesRow) => void
  order: string[]; widths: Record<string, number>; padding: number
}) {
  if (sales.isLoading) return <div className="pm-dsec__hint">Loading sales…</div>
  const rows = sales.data ?? []
  if (rows.length === 0) return <div className="pm-dsec__hint">No recent sales.</div>

  const cell: Record<string, { th: React.ReactNode; num?: boolean; td: (r: SalesRow) => React.ReactNode }> = {
    qty: { th: 'Qty', num: true, td: (r) => num(r.qty) },
    bill: { th: 'Bill', td: (r) => r.bill_no ?? '—' },
    date: { th: 'Date', td: (r) => <span className="sx-dim">{shortDate(r.date)}</span> },
    cust: { th: 'Cust', td: (r) => <span className="pm-mt__ellip">{r.customer ?? '—'}</span> },
    dis: { th: 'Dis%', num: true, td: (r) => (r.discount != null ? `${num(r.discount)}%` : '—') },
    rep: { th: 'Rep', td: (r) => <span className="pm-mt__ellip">{r.salesman ?? '—'}</span> },
  }

  return (
    <div className="pm-minitable-wrap">
      <table className="pm-minitable pm-minitable--click pm-minitable--sales" style={{ '--pm-mt-pad': `${padding}px` } as React.CSSProperties}>
        <colgroup>
          {order.map((id) => <col key={id} style={{ width: `${widths[id] ?? 50}px` }} />)}
        </colgroup>
        <thead>
          <tr>
            {order.map((id) => <th key={id} className={cell[id]?.num ? 'sx-num' : undefined}>{cell[id]?.th}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, limit).map((r, i) => (
            <tr key={`${r.bill_no}-${i}`} onClick={() => onRowClick?.(r)} title="Open sales bill">
              {order.map((id) => <td key={id} className={cell[id]?.num ? 'sx-num' : undefined}>{cell[id]?.td(r)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
