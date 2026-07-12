import { useCallback, useState } from 'react'
import type { PurchaseRow, SalesRow } from '../../types/stock'
import type { SupplierRow, WorkspaceItem } from '../../types/procurement'
import type { BillTarget } from './BillDrawer'
import { stockService } from '../../services/stockService'
import { useStockResource } from '../stock/useStockResource'
import { MovementChart } from '../stock/MovementChart'
import { EmptyState } from '../common/EmptyState'
import { SupplierPicker } from './SupplierPicker'
import { money, num, date } from '../stock/format'
import '../stock/stock-ui.css'

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

/**
 * Right-hand Purchase Decision Panel. Fits entirely inside the viewport (the
 * page never scrolls because of it): the Product header, Sales Trend chart and
 * Supplier Recommendation stay pinned, while Purchase History and Sales History
 * scroll internally at a fixed height. Decision Summary is low-priority and
 * sits at the bottom. Batch / Expiry / PTR / MRP detail belongs to GRN, not the
 * Purchase Manager, so it is intentionally absent here.
 */
/** Real per-supplier offer facts (Supplier Live Stock only — sourced from
 *  procurement.supplier_stock's scheme/free/discount, not the still-unpopulated
 *  WorkspaceItem.offer field). Optional: absent in Review All / Supplier
 *  Purchasing, which have no such per-supplier data source. */
export interface OfferInfo {
  supplierName: string | null
  label: string
  discount?: number | null
}

export function DetailColumn({
  tenantId,
  item,
  onOpenInfo,
  onOpenBill,
  onViewAll,
  assignedSupplier,
  onChangeSupplier,
  onRemoveAssignment,
  offerInfo,
}: {
  tenantId: string
  item: WorkspaceItem | null
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

  if (!item || !hasProduct) {
    return (
      <div className="pm-dpanel pm-dpanel--empty">
        <EmptyState
          icon="bi-hand-index"
          title="Select a product"
          description="Choose a row on the left to see the sales trend, supplier recommendation, recent purchases and sales."
        />
      </div>
    )
  }

  const openInfo = onOpenInfo ? (tab: DrawerTab) => onOpenInfo(item, tab) : undefined

  return (
    <div className="pm-dpanel pm-dpanel--fit" key={item.order_item_id}>
      {/* Product header + view-mode switch (no Mfr/Category/Location clutter) */}
      <header className="pm-dhead">
        <div className="min-w-0">
          <div className="pm-dhead__name">{item.product_name ?? item.product_code ?? '—'}</div>
          <div className="pm-dhead__meta">
            {item.product_code && <span>{item.product_code}</span>}
            {item.unit_description && <span><b>Unit</b>{item.unit_description}</span>}
            {item.pack && <span><b>Pack</b>{item.pack}</span>}
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
        </div>
      </header>

      {viewMode === 'history' ? (
        <HistoryView purchases={purchases} sales={sales} onOpenPurchase={openPurchaseBill} onOpenSales={openSalesBill} />
      ) : (
        <>
          {/* Sales Trend — pinned, always visible */}
          <section className="pm-dsec pm-dsec--trend pm-dsec--fixed">
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

          {/* Purchase History — fixed height, internal scroll. Click a row to
              open its Purchase Bill Drawer. */}
          <section className="pm-dsec pm-dsec--pur pm-dsec--scroll">
            <div className="pm-dsec__title">
              <i className="bi bi-truck" /> Purchase History
              {onViewAll && (
                <button className="pm-linkbtn pm-dsec__titlebtn" onClick={() => onViewAll('purchase')}>
                  View All
                </button>
              )}
            </div>
            <PurchaseMiniTable purchases={purchases} onRowClick={openPurchaseBill} />
          </section>

          {/* Sales History — fixed height, internal scroll. Click a row to open
              its Sales Bill Drawer. */}
          <section className="pm-dsec pm-dsec--sales pm-dsec--scroll">
            <div className="pm-dsec__title">
              <i className="bi bi-cart-check" /> Sales History
              {onViewAll && (
                <button className="pm-linkbtn pm-dsec__titlebtn" onClick={() => onViewAll('sales')}>
                  View All
                </button>
              )}
            </div>
            <SalesMiniTable sales={sales} onRowClick={openSalesBill} />
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
}: {
  purchases: Res<PurchaseRow[]>
  sales: Res<SalesRow[]>
  onOpenPurchase: (r: PurchaseRow) => void
  onOpenSales: (r: SalesRow) => void
}) {
  return (
    <>
      <section className="pm-dsec pm-dsec--pur pm-dsec--scroll pm-dsec--grow">
        <div className="pm-dsec__title"><i className="bi bi-truck" /> Purchase History</div>
        <PurchaseMiniTable purchases={purchases} limit={100} onRowClick={onOpenPurchase} />
      </section>
      <section className="pm-dsec pm-dsec--sales pm-dsec--scroll pm-dsec--grow">
        <div className="pm-dsec__title"><i className="bi bi-cart-check" /> Sales History</div>
        <SalesMiniTable sales={sales} limit={100} onRowClick={onOpenSales} />
      </section>
    </>
  )
}

/* ---- Compact grids -------------------------------------------------------- */

function PurchaseMiniTable({
  purchases, limit = 50, onRowClick,
}: { purchases: Res<PurchaseRow[]>; limit?: number; onRowClick?: (r: PurchaseRow) => void }) {
  if (purchases.isLoading) return <div className="pm-dsec__hint">Loading purchases…</div>
  const rows = purchases.data ?? []
  if (rows.length === 0) return <div className="pm-dsec__hint">No recent purchases.</div>
  return (
    <div className="pm-minitable-wrap">
      <table className="pm-minitable pm-minitable--click">
        <thead>
          <tr>
            <th>Date</th><th>Supplier</th>
            <th className="sx-num">Qty</th><th className="sx-num">Free</th>
            <th className="sx-num">Item Cost</th><th className="sx-num">PTR</th>
            <th className="sx-num">MRP</th>
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, limit).map((r, i) => (
            <tr key={`${r.grn_no}-${i}`} onClick={() => onRowClick?.(r)} title="Open purchase bill">
              <td className="sx-dim">{date(r.date)}</td>
              <td className="pm-mt__ellip">{r.supplier ?? '—'}</td>
              <td className="sx-num">{num(r.qty)}</td>
              <td className="sx-num">{num(r.free)}</td>
              <td className="sx-num">{money(r.cost)}</td>
              <td className="sx-num">{money(r.ptr)}</td>
              <td className="sx-num">{money(r.mrp)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SalesMiniTable({
  sales, limit = 50, onRowClick,
}: { sales: Res<SalesRow[]>; limit?: number; onRowClick?: (r: SalesRow) => void }) {
  if (sales.isLoading) return <div className="pm-dsec__hint">Loading sales…</div>
  const rows = sales.data ?? []
  if (rows.length === 0) return <div className="pm-dsec__hint">No recent sales.</div>
  return (
    <div className="pm-minitable-wrap">
      <table className="pm-minitable pm-minitable--click">
        <thead>
          <tr>
            <th>Date</th><th>Bill</th><th>Customer</th>
            <th className="sx-num">Qty</th><th>Rep</th>
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, limit).map((r, i) => (
            <tr key={`${r.bill_no}-${i}`} onClick={() => onRowClick?.(r)} title="Open sales bill">
              <td className="sx-dim">{date(r.date)}</td>
              <td>{r.bill_no ?? '—'}</td>
              <td className="pm-mt__ellip">{r.customer ?? '—'}</td>
              <td className="sx-num">{num(r.qty)}</td>
              <td className="pm-mt__ellip">{r.salesman ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

