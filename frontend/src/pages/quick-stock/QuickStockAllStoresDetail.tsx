import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { QuickStockChart } from './QuickStockChart'
import { SalesSummaryGrid } from './SalesSummaryGrid'
import { quickStockService } from './quickStockService'
import { useScrollSync } from './useScrollSync'
import type {
  QuickStockBatchRow,
  QuickStockBillItem,
  QuickStockCore,
  QuickStockCoreBulkItem,
  QuickStockGrnItem,
  QuickStockPurchaseRow,
  QuickStockSalesRow,
} from './types'

export interface QuickStockColumnTarget {
  storeId: string
  storeLabel: string
  /** Full store name when the shell has one. */
  storeName?: string | null
  productCode: string
  /** Already returned by search or cross-store match. Omitted when unknown. */
  productName?: string | null
  saleUnit?: string | null
}

/** Display-only batch cutoff. Zero, negative, and below-minimum rows stay in
 *  the fetched list and are omitted from the Quick Stock batch modal. */
export const DEFAULT_BATCH_MIN_STOCK = 5

export function qualifyingBatches(rows: QuickStockBatchRow[], minimum: number) {
  const min = Number.isFinite(minimum) ? minimum : DEFAULT_BATCH_MIN_STOCK
  return rows.filter((row) => {
    const stock = Number(row.stock)
    return Number.isFinite(stock) && stock > 0 && stock >= min
  })
}

function money(v: number | null | undefined) {
  if (v == null) return '—'
  return v.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function date(v: string | null | undefined) {
  if (!v) return '—'
  const d = new Date(v)
  return Number.isNaN(d.getTime()) ? v : d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: '2-digit' })
}

interface GrnDrawerState {
  storeLabel: string
  grnNo: string
  supplier: string | null
}

export interface BatchDrawerState {
  storeLabel: string
  productName: string | null
  rows: QuickStockBatchRow[]
}

/** Closes a modal or the sales detail card on Escape. */
function useEscapeToClose(onClose: () => void) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])
}

interface SaleSelection {
  key: string
  store: QuickStockColumnTarget
  sale: QuickStockSalesRow
}

function textValue(value: unknown): string | null {
  if (value == null) return null
  const text = String(value).trim()
  if (!text || text === '-' || text === '—') return null
  return text
}

function existingSaleRate(row: object | null | undefined): number | string | null {
  if (!row) return null
  const rec = row as Record<string, unknown>
  for (const key of ['sale_rate', 'saleRate', 'selling_rate', 'sellingRate']) {
    const value = rec[key]
    if (typeof value === 'number' && Number.isFinite(value)) return value
    const text = textValue(value)
    if (text) return text
  }
  return null
}

/** Full bill-detail modal for one sales row: a Bill Header section (store,
 * date, customer, bill number, salesman) and a Bill Product Details grid
 * covering EVERY product on that bill — not just the clicked one — fetched
 * once via the existing bill-items API (already grouped per product there).
 * A Bill Summary footer reconciles item/qty/discount/grand-total. */
function SaleDetailCard({
  tenantId,
  selection,
  onClose,
}: {
  tenantId: string
  selection: SaleSelection
  anchorEl: HTMLElement | null
  onClose: () => void
}) {
  const [items, setItems] = useState<QuickStockBillItem[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)
  const { store, sale } = selection
  useEscapeToClose(onClose)

  useEffect(() => {
    if (!sale.bill_no) {
      setItems(null)
      setLoading(false)
      setError(true)
      return
    }
    let live = true
    setLoading(true)
    setItems(null)
    setError(false)
    quickStockService
      .billItems(tenantId, store.storeId, sale.bill_no, sale.date)
      .then((rows) => { if (live) setItems(rows) })
      .catch(() => { if (live) setError(true) })
      .finally(() => { if (live) setLoading(false) })
    return () => { live = false }
  }, [tenantId, store.storeId, sale.bill_no, sale.date])

  const rows = items ?? []
  const salesman = textValue((sale as QuickStockSalesRow & { salesman?: string | null }).salesman)
    ?? (rows.length > 0 && rows.every((row) => textValue(row.salesman) === textValue(rows[0]?.salesman))
      ? textValue(rows[0]?.salesman)
      : null)
  const totalItems = rows.length
  const totalQty = rows.reduce((sum, r) => sum + (Number(r.qty) || 0), 0)
  const grandTotal = rows.reduce((sum, r) => sum + (Number(r.amount) || 0), 0)
  // Weighted average discount, since the grid shows a per-line percentage
  // but the footer needs one reconciled figure for the whole bill.
  const totalDiscount = rows.reduce((sum, r) => {
    const base = (Number(r.mrp) || 0) * (Number(r.qty) || 0)
    return sum + base * ((Number(r.discount_pct) || 0) / 100)
  }, 0)

  return createPortal(
    <div className="qs-bill-modal-overlay" onClick={onClose}>
      <div
        className="qs-bill-modal"
        role="dialog"
        aria-label={`Bill ${sale.bill_no ?? ''} · ${store.storeLabel}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="qs-bill-modal__head">
          <strong>Bill Details</strong>
          <button type="button" className="qs-close-btn" onClick={onClose}>✕ Close</button>
        </div>

        <div className="qs-bill-modal__body">
          <section className="qs-bill-header">
            <div className="qs-bill-header__title">Bill Header</div>
            <div className="qs-bill-header__grid">
              <div className="qs-bill-header__field"><span>Store Code</span><strong>{store.storeLabel}</strong></div>
              <div className="qs-bill-header__field"><span>Store Name</span><strong>{store.storeName ?? '—'}</strong></div>
              <div className="qs-bill-header__field"><span>Transaction Date</span><strong>{date(sale.date)}</strong></div>
              <div className="qs-bill-header__field"><span>Customer Name</span><strong>{textValue(sale.customer) ?? '—'}</strong></div>
              <div className="qs-bill-header__field"><span>Bill Number</span><strong>{sale.bill_no ?? '—'}</strong></div>
              <div className="qs-bill-header__field"><span>Salesman</span><strong>{salesman ?? '—'}</strong></div>
            </div>
          </section>

          <section className="qs-bill-products">
            <div className="qs-bill-products__title">Bill Product Details</div>
            {loading ? (
              <div className="qs-panel__empty">Loading bill detail…</div>
            ) : error ? (
              <div className="qs-panel__empty">Could not load this bill. Please try again.</div>
            ) : rows.length === 0 ? (
              <div className="qs-panel__empty">No products found for this bill.</div>
            ) : (
              <div className="qs-bill-products__scroll">
                <table className="qs-bill-grid">
                  <thead>
                    <tr>
                      <th>S.No</th>
                      <th>Product Code</th>
                      <th>Product Name</th>
                      <th>Unit</th>
                      <th className="qs-num">Quantity</th>
                      <th className="qs-num">MRP</th>
                      <th className="qs-num">Discount</th>
                      <th className="qs-num">Rate</th>
                      <th className="qs-num">Amount</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row, i) => {
                      const rate = existingSaleRate(row)
                      return (
                        <tr key={`${row.product_code ?? row.product_name ?? i}`}>
                          <td>{row.line_no ?? i + 1}</td>
                          <td>{row.product_code ?? '—'}</td>
                          <td>{row.product_name ?? '—'}</td>
                          <td>{row.sale_unit ?? '—'}</td>
                          <td className="qs-num">{row.qty ?? 0}</td>
                          <td className="qs-num">{money(row.mrp)}</td>
                          <td className="qs-num">{row.discount_pct != null ? `${row.discount_pct}%` : '—'}</td>
                          <td className="qs-num">{typeof rate === 'number' ? money(rate) : (rate ?? '—')}</td>
                          <td className="qs-num">{money(row.amount)}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>

        <div className="qs-bill-summary">
          <div className="qs-bill-summary__item"><span>Total Items</span><strong>{totalItems}</strong></div>
          <div className="qs-bill-summary__item"><span>Total Quantity</span><strong>{totalQty.toLocaleString('en-IN')}</strong></div>
          <div className="qs-bill-summary__item"><span>Total Discount</span><strong>{money(totalDiscount)}</strong></div>
          <div className="qs-bill-summary__item qs-bill-summary__item--grand"><span>Grand Total</span><strong>{money(grandTotal)}</strong></div>
        </div>
      </div>
    </div>,
    document.body,
  )
}

function GrnDrawer({
  tenantId,
  storeId,
  state,
  onClose,
}: {
  tenantId: string
  storeId: string
  state: GrnDrawerState
  onClose: () => void
}) {
  const [items, setItems] = useState<QuickStockGrnItem[] | null>(null)
  const [loading, setLoading] = useState(true)
  useEscapeToClose(onClose)

  useEffect(() => {
    let live = true
    setLoading(true)
    quickStockService
      .purchaseBill(tenantId, storeId, state.grnNo)
      .then((rows) => { if (live) setItems(rows) })
      .finally(() => { if (live) setLoading(false) })
    return () => { live = false }
  }, [tenantId, storeId, state.grnNo])

  const total = (items ?? []).reduce((sum, r) => sum + (r.qty ?? 0) * (r.ptr ?? 0), 0)

  return (
    <div className="qs-modal-overlay" onClick={onClose}>
      <div className="qs-modal" onClick={(e) => e.stopPropagation()}>
        <div className="qs-modal__head">
          <strong>{state.storeLabel} — GRN {state.grnNo}{state.supplier ? ` · ${state.supplier}` : ''}</strong>
          <button type="button" className="qs-close-btn" onClick={onClose}>✕ Close</button>
        </div>
        <div className="qs-modal__body">
          {loading ? (
            <div className="qs-panel__empty">Loading…</div>
          ) : items && items.length > 0 ? (
            <>
              <table className="qs-line">
                <thead>
                  <tr><th>Product</th><th>Batch</th><th>Expiry</th><th className="qs-num">Qty</th><th className="qs-num">Free</th><th className="qs-num">PTR</th><th className="qs-num">MRP</th></tr>
                </thead>
                <tbody>
                  {items.map((r, i) => (
                    <tr key={i}>
                      <td>{r.product_name ?? '—'}</td>
                      <td>{r.batch ?? '—'}</td>
                      <td>{date(r.expiry)}</td>
                      <td className="qs-num">{r.qty ?? 0}</td>
                      <td className="qs-num">{r.free ?? 0}</td>
                      <td className="qs-num">{money(r.ptr)}</td>
                      <td className="qs-num">{money(r.mrp)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="qs-modal__total">GRN value: <strong>{money(total)}</strong></div>
            </>
          ) : (
            <div className="qs-panel__empty">No line items found for this GRN.</div>
          )}
        </div>
      </div>
    </div>
  )
}

/** Batch & expiry modal, opened by double-clicking a product row in the
 * STORE GRID band for one specific store. Closes on overlay-click or
 * Escape. */
export function BatchDrawer({ state, onClose }: { state: BatchDrawerState; onClose: () => void }) {
  const [minimum, setMinimum] = useState(DEFAULT_BATCH_MIN_STOCK)
  useEscapeToClose(onClose)
  const minStock = Number.isFinite(minimum) ? minimum : DEFAULT_BATCH_MIN_STOCK
  const shown = qualifyingBatches(state.rows, minStock)

  return (
    <div className="qs-modal-overlay" onClick={onClose}>
      <div
        className="qs-modal"
        data-batch-unfiltered={state.rows.length}
        data-batch-shown={shown.length}
        data-batch-min={minStock}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="qs-modal__head">
          <strong>{state.storeLabel} — {state.productName ?? 'Product'} · Batch &amp; Expiry</strong>
          <label className="qs-batch-min">
            Min stock
            <input
              type="number"
              min={0}
              step={1}
              aria-label="Minimum batch stock"
              value={Number.isFinite(minimum) ? minimum : ''}
              onChange={(event) => {
                const next = event.target.value
                if (next === '') {
                  setMinimum(Number.NaN)
                  return
                }
                const parsed = Number(next)
                setMinimum(Number.isFinite(parsed) ? parsed : DEFAULT_BATCH_MIN_STOCK)
              }}
            />
          </label>
          <button type="button" className="qs-close-btn" onClick={onClose}>✕ Close</button>
        </div>
        <div className="qs-modal__body">
          {shown.length > 0 ? (
            <table className="qs-line">
              <thead>
                <tr><th>Batch</th><th className="qs-num">Stock</th><th>Expiry</th><th className="qs-num">PTR</th><th className="qs-num">MRP</th></tr>
              </thead>
              <tbody>
                {shown.map((b, i) => (
                  <tr key={i}>
                    <td title={b.batch_no ?? undefined}>{b.batch_no ?? '—'}</td>
                    <td className="qs-num" title={String(b.stock ?? 0)}>{b.stock ?? 0}</td>
                    <td title={date(b.expiry_date)}>{date(b.expiry_date)}</td>
                    <td className="qs-num" title={money(b.ptr)}>{money(b.ptr)}</td>
                    <td className="qs-num" title={money(b.mrp)}>{money(b.mrp)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="qs-panel__empty">
              {state.rows.length > 0
                ? `No batches with stock ≥ ${minStock}.`
                : 'No batch rows.'}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

/** Fetches the detail bundle (chart movement + batches + ONLY the active
 * Sales-or-Purchase transactions) for EVERY active target in a single bulk
 * request, keyed by store id — replaces the old one-HTTP-request-per-store
 * approach, where N stores' identical heavy queries ran concurrently and
 * contended on the DB, leaving most stores stuck on "Loading..."
 * indefinitely while only the first 1-2 finished.
 *
 * Sales and Purchase are fetched independently (productCoreBulkSplit, mode =
 * detailMode) so switching the toggle never loads the type that isn't shown;
 * a small per-(search, mode) cache means switching BACK to an
 * already-fetched mode is instant and does not re-request it. The cache is
 * cleared whenever the search/tenant/store set changes (a new `key`), so a
 * product-search or tenant/store change can never show stale data under the
 * new target.
 *
 * Batch & expiry data for the on-demand batch modal (BatchDrawer /
 * openBatchForStore in QuickStockPage) stays its own separate fetch, same as
 * before -- it is only needed on double-click, not for every store up
 * front. */
type AllStoresCoreCache = Map<string, Map<'sales' | 'purchase', QuickStockCoreBulkItem[]>>

function useAllStoresCore(tenantId: string, targets: QuickStockColumnTarget[], detailMode: 'sales' | 'purchase') {
  const [coreByStore, setCoreByStore] = useState<Map<string, QuickStockCore>>(new Map())
  const [loading, setLoading] = useState(targets.length > 0)
  const key = `${tenantId}|${targets.map((t) => `${t.storeId}:${t.productCode}`).join('|')}`
  const cacheRef = useRef<AllStoresCoreCache>(new Map())
  const lastKeyRef = useRef(key)

  // A new search/tenant/store set invalidates every cached mode for the
  // PREVIOUS key -- the old rows must never be shown under a new target.
  if (lastKeyRef.current !== key) {
    cacheRef.current = new Map()
    lastKeyRef.current = key
  }

  useEffect(() => {
    if (targets.length === 0) {
      setCoreByStore(new Map())
      setLoading(false)
      return undefined
    }
    const items = targets.map((t) => ({ store_id: t.storeId, product_code: t.productCode }))
    const byMode = cacheRef.current.get(key) ?? new Map<'sales' | 'purchase', QuickStockCoreBulkItem[]>()
    cacheRef.current.set(key, byMode)

    const cached = byMode.get(detailMode)
    if (cached) {
      setCoreByStore(new Map(cached.map((item) => [item.store_id, item])))
      setLoading(false)
      return undefined
    }

    let live = true
    setLoading(true)
    quickStockService
      .productCoreBulkSplit(tenantId, items, detailMode, 4)
      .then(({ items: fetched }) => {
        if (!live) return
        byMode.set(detailMode, fetched)
        setCoreByStore(new Map(fetched.map((item) => [item.store_id, item])))
      })
      .finally(() => { if (live) setLoading(false) })
    return () => { live = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId, key, detailMode])

  return { coreByStore, loading }
}

/**
 * Renders the CHART band and the Sales/Purchase band (whichever the toggle
 * selects) of the Quick Stock row-band matrix: a label strip per band
 * (placed by the caller's grid column 1) plus, per store column, one cell
 * per band — all positioned by explicit `gridRow`/`gridColumn` so they land
 * in the exact grid rows the page component (`QuickStockPage`) has reserved
 * for them, continuing the same `.qs-scm` grid the STORE GRID band occupies
 * above.
 *
 * Only stores with their OWN matching product in the current search results
 * get a target (and therefore a real fetch) — there is no cross-store
 * resolution step and no "pending" state; a store with no match for this
 * query simply renders "Not stocked here."
 */
export function QuickStockAllStoresDetail({
  tenantId,
  targets,
  restrictedStoreIds,
  detailMode,
  rowOf,
  columnOf,
  labelColumn,
}: {
  tenantId: string
  targets: QuickStockColumnTarget[]
  /** Store ids whose Chart/Purchase/Sales detail is withheld (e.g. NMW
   * warehouse for a non-super-admin) — their stock/MRP already showed in the
   * STORE GRID band above; this only gates the per-store detail fetch. */
  restrictedStoreIds?: Set<string>
  /** Which band occupies the shared third row: Sales or Purchase. */
  detailMode: 'sales' | 'purchase'
  /** Grid row index (1-based, matching the page's grid-template-rows) for
   * each band, supplied by QuickStockPage so this component never has to
   * know the overall row numbering itself. */
  rowOf: Record<'chart' | 'detail', number>
  /** Grid column index (1-based) for a given store id, supplied by the page
   * so columns line up exactly under the STORE GRID header above. */
  columnOf: (storeId: string) => number
  /** Grid column index of the left label strip (always 1 in practice). */
  labelColumn: number
}) {
  const [saleSelection, setSaleSelection] = useState<SaleSelection | null>(null)
  const [saleAnchor, setSaleAnchor] = useState<HTMLElement | null>(null)
  const [grnDrawer, setGrnDrawer] = useState<{ store: QuickStockColumnTarget; state: GrnDrawerState } | null>(null)
  // Restricted stores are never fetched (not just hidden) -- a non-admin
  // never pulls NMW's purchase/sales rows over the wire.
  const fetchTargets = restrictedStoreIds
    ? targets.filter((t) => !restrictedStoreIds.has(t.storeId))
    : targets
  const { coreByStore, loading } = useAllStoresCore(tenantId, fetchTargets, detailMode)
  // Keeps every store's Purchase/Sales cell scrolled together — same reason
  // as the Store Grid band's sync in QuickStockPage.tsx.
  const detailScrollRef = useScrollSync()
  const closeSale = useCallback(() => {
    setSaleSelection(null)
    setSaleAnchor(null)
  }, [])

  useEffect(() => {
    if (detailMode !== 'sales') closeSale()
  }, [detailMode, closeSale])

  useEffect(() => {
    if (!saleSelection) return
    const stillThere = targets.some(
      (t) => t.storeId === saleSelection.store.storeId && t.productCode === saleSelection.store.productCode,
    )
    if (!stillThere) closeSale()
  }, [targets, saleSelection, closeSale])

  return (
    <>
      <div className="qs-rowlabel qs-rowlabel--chart" style={{ gridRow: rowOf.chart, gridColumn: labelColumn }}>
        <span>Chart</span>
      </div>
      <div className={`qs-rowlabel qs-rowlabel--${detailMode}`} style={{ gridRow: rowOf.detail, gridColumn: labelColumn }}>
        <span>{detailMode === 'sales' ? 'Sales' : 'Purchase'}</span>
      </div>

      {targets.map((t) => (
        <StoreCoreCellsWithColumn
          key={t.storeId}
          target={t}
          core={coreByStore.get(t.storeId) ?? null}
          loading={loading}
          restricted={Boolean(restrictedStoreIds?.has(t.storeId))}
          rows={rowOf}
          column={columnOf(t.storeId)}
          detailScrollRef={detailScrollRef}
          detailMode={detailMode}
          selectedSaleKey={saleSelection?.key ?? null}
          onSelectSale={(store, sale, key, anchor) => {
            setSaleSelection({ key, store, sale })
            setSaleAnchor(anchor)
          }}
          onOpenGrn={(store, purchase) =>
            setGrnDrawer({ store, state: { storeLabel: store.storeLabel, grnNo: purchase.grn_no ?? '', supplier: purchase.supplier ?? null } })
          }
        />
      ))}

      {detailMode === 'sales' && saleSelection && (
        <SaleDetailCard
          tenantId={tenantId}
          selection={saleSelection}
          anchorEl={saleAnchor}
          onClose={closeSale}
        />
      )}

      {grnDrawer && (
        <GrnDrawer
          tenantId={tenantId}
          storeId={grnDrawer.store.storeId}
          state={grnDrawer.state}
          onClose={() => setGrnDrawer(null)}
        />
      )}
    </>
  )
}

/** Both cells (chart + sales-or-purchase) for one store share the same
 * bulk-fetched `core`; each cell sets its own `gridColumn` to line up under
 * that store's header, and `gridRow` comes from the page's row map (`rows`). */
function StoreCoreCellsWithColumn(props: {
  target: QuickStockColumnTarget
  core: QuickStockCore | null
  loading: boolean
  /** NMW for a non-super-admin: stock/MRP already shown in STORE GRID above;
   * Chart/Purchase/Sales are withheld here instead of showing fetched data. */
  restricted: boolean
  rows: Record<'chart' | 'detail', number>
  column: number
  detailScrollRef: (key: string) => (el: HTMLDivElement | null) => void
  detailMode: 'sales' | 'purchase'
  selectedSaleKey: string | null
  onSelectSale: (store: QuickStockColumnTarget, sale: QuickStockSalesRow, key: string, anchor: HTMLElement) => void
  onOpenGrn: (store: QuickStockColumnTarget, purchase: QuickStockPurchaseRow) => void
}) {
  const { target, core, loading, restricted, rows, column, detailScrollRef, detailMode, selectedSaleKey, onSelectSale, onOpenGrn } = props

  if (restricted) {
    return (
      <>
        <div className="qs-cell qs-cell--chart" style={{ gridRow: rows.chart, gridColumn: column }}>
          <div className="qs-panel__empty">Warehouse chart — super admin only</div>
        </div>
        <div className={`qs-cell qs-cell--${detailMode}`} style={{ gridRow: rows.detail, gridColumn: column }}>
          <div className="qs-panel__empty">Warehouse {detailMode} — super admin only</div>
        </div>
      </>
    )
  }

  return (
    <>
      <div className="qs-cell qs-cell--chart" style={{ gridRow: rows.chart, gridColumn: column }}>
        {loading ? <div className="qs-panel__empty">Loading…</div> : <QuickStockChart movement={core?.movement ?? []} />}
      </div>
      {detailMode === 'purchase' ? (
        <div
          className="qs-cell qs-cell--purchase"
          ref={detailScrollRef(target.storeId)}
          style={{ gridRow: rows.detail, gridColumn: column }}
        >
          {loading ? (
            <div className="qs-panel__empty">Loading…</div>
          ) : core?.purchases?.length ? (
            <table className="qs-line">
              <thead>
                <tr><th>Date</th><th>GRN</th><th className="qs-num">Qty</th><th className="qs-num">Free</th><th className="qs-num">PTR</th><th className="qs-num">MRP</th></tr>
              </thead>
              <tbody>
                {core.purchases.slice(0, 10).map((p, i) => (
                  <tr
                    key={i}
                    className="qs-row-clickable"
                    onClick={(e) => { e.stopPropagation(); if (p.grn_no) onOpenGrn(target, p) }}
                  >
                    <td title={date(p.date)}>{date(p.date)}</td>
                    <td title={p.grn_no ?? undefined}>{p.grn_no ?? '—'}</td>
                    <td className="qs-num" title={String(p.qty ?? 0)}>{p.qty ?? 0}</td>
                    <td className="qs-num" title={String(p.free ?? 0)}>{p.free ?? 0}</td>
                    <td className="qs-num" title={money(p.ptr)}>{money(p.ptr)}</td>
                    <td className="qs-num" title={money(p.mrp)}>{money(p.mrp)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <div className="qs-panel__empty">Not stocked here.</div>}
        </div>
      ) : (
        <div
          className="qs-cell qs-cell--sales"
          ref={detailScrollRef(target.storeId)}
          style={{ gridRow: rows.detail, gridColumn: column }}
        >
          {loading ? (
            <div className="qs-panel__empty">Loading…</div>
          ) : core?.sales?.length ? (
            <SalesSummaryGrid
              ariaLabel={`${target.storeLabel} sales`}
              selectedKey={selectedSaleKey}
              rows={core.sales.slice(0, 20).map((s, i) => ({
                key: `${target.storeId}|${i}|${s.date ?? ''}|${s.bill_no ?? ''}|${s.qty ?? ''}`,
                date: date(s.date),
                qty: String(s.qty ?? 0),
                customer: s.customer?.trim() ?? '',
              }))}
              onSelect={(key, anchor) => {
                const sale = core.sales.slice(0, 20).find((s, i) =>
                  `${target.storeId}|${i}|${s.date ?? ''}|${s.bill_no ?? ''}|${s.qty ?? ''}` === key)
                if (sale) onSelectSale(target, sale, key, anchor)
              }}
            />
          ) : <div className="qs-panel__empty">No recent bills.</div>}
        </div>
      )}
    </>
  )
}
