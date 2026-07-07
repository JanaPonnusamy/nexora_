import { useCallback } from 'react'
import type { ProductContext, SalesRow } from '../../types/stock'
import { stockService } from '../../services/stockService'
import { EmptyState } from '../common/EmptyState'
import { ErrorState } from '../common/ErrorState'
import { TableSkeleton } from '../common/TableSkeleton'
import { SxCard, SxCardHead, SxCardBody, SxTable } from '../sync/ui'
import { useStockResource } from './useStockResource'
import { MovementChart } from './MovementChart'
import { money, num, date } from './format'

function panelKey(ctx: ProductContext | null): string | null {
  return ctx ? `${ctx.tenantId}|${ctx.storeId}|${ctx.productCode}` : null
}

/* ---- Expiry helpers ------------------------------------------------------- */

type ExpiryStatus = 'expired' | 'soon' | 'ok' | 'none'

function expiryStatus(expiryDate: string | null | undefined): ExpiryStatus {
  if (!expiryDate) return 'none'
  const exp = new Date(expiryDate)
  if (isNaN(exp.getTime())) return 'none'
  const diffDays = (exp.getTime() - Date.now()) / (1000 * 60 * 60 * 24)
  if (diffDays < 0) return 'expired'
  if (diffDays <= 90) return 'soon'
  return 'ok'
}

function ExpiryBadge({ expiryDate }: { expiryDate: string | null | undefined }) {
  const status = expiryStatus(expiryDate)
  const label = date(expiryDate)
  if (status === 'none') return <span className="sx-dim">—</span>
  return <span className={`sa-expiry sa-expiry--${status}`}>{label}</span>
}

/* ---- Inline stock bar (under the qty number) ------------------------------ */

function InlineStockBar({ value, max }: { value: number; max: number }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0
  return (
    <span className="sa-inbar">
      <span className="sa-inbar__fill" style={{ width: `${pct}%` }} />
    </span>
  )
}

/* ---- Last-sale recency label --------------------------------------------- */

function recencyLabel(d: string | null | undefined): string | null {
  if (!d) return null
  const parsed = new Date(d)
  if (isNaN(parsed.getTime())) return null
  const days = Math.floor((Date.now() - parsed.getTime()) / (1000 * 60 * 60 * 24))
  if (days === 0) return 'Today'
  if (days === 1) return 'Yesterday'
  if (days < 7) return `${days}d ago`
  if (days < 30) return `${Math.floor(days / 7)}w ago`
  if (days < 365) return `${Math.floor(days / 30)}mo ago`
  return `${Math.floor(days / 365)}y ago`
}

/* ---- Product context bar ------------------------------------------------- */

export function ProductContextBar({ ctx }: { ctx: ProductContext }) {
  const fetcher = useCallback(
    () => stockService.productDetails(ctx.tenantId, ctx.storeId, ctx.productCode),
    [ctx.tenantId, ctx.storeId, ctx.productCode],
  )
  const { data } = useStockResource(fetcher, panelKey(ctx))
  const stock = data?.total_stock ?? ctx.stock
  const recency = recencyLabel(data?.last_sale)

  return (
    <div className="sa-ctx">
      <div className="sa-ctx__lead">
        <i className="bi bi-box-seam" aria-hidden="true" />
        <strong>{ctx.productName ?? ctx.productCode}</strong>
        <span className="sa-tag">{ctx.storeCode ?? ctx.storeName}</span>
        <span className={`sa-tag sa-tag--stock${stock <= 0 ? ' sa-tag--stock-out' : ''}`}>
          <span className={`sa-dot sa-dot--${stock > 0 ? 'in' : 'out'}`} aria-hidden="true" />
          Stock {num(stock)}
        </span>
      </div>
      <div className="sa-ctx__stats">
        <span className="sa-ctx__stat"><b>MRP</b>{money(data?.mrp)}</span>
        <span className="sa-ctx__stat"><b>Sale Unit</b>{data?.sale_unit ?? '—'}</span>
        <span className="sa-ctx__stat"><b>Packing</b>{data?.packing != null ? num(data.packing) : '—'}</span>
        <span className="sa-ctx__stat"><b>Sub-Loc</b>{data?.sublocation ?? '—'}</span>
        <span className="sa-ctx__stat">
          <b>Last Sale</b>
          {date(data?.last_sale)}
          {recency && <em className="sa-ctx__recency-badge">{recency}</em>}
        </span>
        <span className="sa-ctx__stat"><b>Last Purchase</b>{date(data?.last_purchase)}</span>
      </div>
    </div>
  )
}

/* ---- Monthly Movement ---------------------------------------------------- */

export function MovementPanel({ ctx }: { ctx: ProductContext }) {
  const fetcher = useCallback(
    () => stockService.monthlyMovement(ctx.tenantId, ctx.storeId, ctx.productCode, 4),
    [ctx.tenantId, ctx.storeId, ctx.productCode],
  )
  const { data, isLoading, error, reload } = useStockResource(fetcher, panelKey(ctx))

  // MoM trend — only show when prev month is non-zero (avoid divide-by-zero noise)
  const trend = (() => {
    if (!data || data.length < 2) return null
    const cur = data[data.length - 1]
    const prev = data[data.length - 2]
    const purChg = (prev.pur ?? 0) > 0 ? (((cur.pur ?? 0) - (prev.pur ?? 0)) / (prev.pur ?? 1)) * 100 : null
    const salChg = (prev.sal ?? 0) > 0 ? (((cur.sal ?? 0) - (prev.sal ?? 0)) / (prev.sal ?? 1)) * 100 : null
    return (purChg !== null || salChg !== null) ? { purChg, salChg } : null
  })()

  return (
    <SxCard className="sa-chart-card">
      <SxCardHead
        title="Monthly Movement"
        icon="bi-bar-chart-line"
        sub={
          <span className="sa-chart-sub">
            Last 4 months
            {trend && (
              <span className="sa-trend-badges">
                {trend.purChg !== null && (
                  <span className={`sa-trend ${trend.purChg >= 0 ? 'sa-trend--up' : 'sa-trend--down'}`}>
                    <i className={`bi bi-arrow-${trend.purChg >= 0 ? 'up' : 'down'}-short`} />
                    PUR {Math.abs(trend.purChg).toFixed(0)}%
                  </span>
                )}
                {trend.salChg !== null && (
                  <span className={`sa-trend ${trend.salChg >= 0 ? 'sa-trend--up-green' : 'sa-trend--down'}`}>
                    <i className={`bi bi-arrow-${trend.salChg >= 0 ? 'up' : 'down'}-short`} />
                    SAL {Math.abs(trend.salChg).toFixed(0)}%
                  </span>
                )}
              </span>
            )}
          </span>
        }
      />
      <SxCardBody>
        {isLoading ? (
          <TableSkeleton rows={4} columns={3} />
        ) : error ? (
          <ErrorState description={error} onRetry={reload} />
        ) : !data || data.length === 0 ? (
          <EmptyState icon="bi-bar-chart" title="No movement" description="No transaction movement found." />
        ) : (
          <MovementChart rows={data} />
        )}
      </SxCardBody>
    </SxCard>
  )
}

/* ---- Batch Details -------------------------------------------------------
   Columns: Batch No · Expiry · Stock (+ inline bar) · MRP
   4 cols — fits the narrow panel without truncation.
--------------------------------------------------------------------------- */

export function BatchPanel({ ctx }: { ctx: ProductContext }) {
  const fetcher = useCallback(
    () => stockService.batchDetails(ctx.tenantId, ctx.storeId, ctx.productCode),
    [ctx.tenantId, ctx.storeId, ctx.productCode],
  )
  const { data, isLoading, error, reload } = useStockResource(fetcher, panelKey(ctx))

  const maxStock = data ? Math.max(1, ...data.map(r => r.stock ?? 0)) : 1
  const expiredCount = data ? data.filter(r => expiryStatus(r.expiry_date) === 'expired').length : 0
  const soonCount   = data ? data.filter(r => expiryStatus(r.expiry_date) === 'soon').length : 0

  const sub = data && data.length > 0 ? (
    <span className="sa-panel-sub">
      {data.length} batch{data.length !== 1 ? 'es' : ''}
      {expiredCount > 0 && <span className="sa-badge sa-badge--danger"><i className="bi bi-exclamation-triangle-fill" /> {expiredCount} expired</span>}
      {soonCount > 0   && <span className="sa-badge sa-badge--warning"><i className="bi bi-clock-fill" /> {soonCount} expiring soon</span>}
    </span>
  ) : undefined

  return (
    <SxCard>
      <SxCardHead title="Batch Details" icon="bi-layers" sub={sub} />
      <SxCardBody flush>
        {isLoading ? (
          <div className="p-3"><TableSkeleton rows={4} columns={4} /></div>
        ) : error ? (
          <ErrorState description={error} onRetry={reload} />
        ) : !data || data.length === 0 ? (
          <EmptyState icon="bi-layers" title="No batches" description="No batch stock found." />
        ) : (
          <SxTable>
            <colgroup>
              <col style={{ width: '72px' }} />   {/* Batch No */}
              <col />                              {/* Expiry — flexible */}
              <col style={{ width: '62px' }} />   {/* Stock + bar */}
              <col style={{ width: '62px' }} />   {/* MRP */}
            </colgroup>
            <thead>
              <tr>
                <th>Batch</th>
                <th>Expiry</th>
                <th className="sx-num">Stock</th>
                <th className="sx-num">MRP</th>
              </tr>
            </thead>
            <tbody>
              {data.map((row, i) => {
                const status = expiryStatus(row.expiry_date)
                return (
                  <tr key={`${row.batch_no}-${i}`} className={`sa-batch-row sa-batch-row--${status}`}>
                    <td className="sa-batch-no">{row.batch_no ?? '—'}</td>
                    <td><ExpiryBadge expiryDate={row.expiry_date} /></td>
                    {/* Stock qty + inline bar stacked */}
                    <td className="sx-num">
                      <span className="sa-stock-cell">
                        <span className="sa-batch-stock">{num(row.stock)}</span>
                        <InlineStockBar value={row.stock ?? 0} max={maxStock} />
                      </span>
                    </td>
                    <td className="sx-num">{money(row.mrp)}</td>
                  </tr>
                )
              })}
            </tbody>
          </SxTable>
        )}
      </SxCardBody>
    </SxCard>
  )
}

/* ---- Recent Sales --------------------------------------------------------
   Columns: Date · Bill No · Customer · Qty
   4 cols — customer truncates gracefully, no disc% (visible in Bill panel).
   Click a row → loads that bill in the Bill Details panel.
--------------------------------------------------------------------------- */

export function SalesPanel({
  ctx, onSelect, activeBillNo,
}: {
  ctx: ProductContext
  onSelect?: (row: SalesRow) => void
  activeBillNo?: string | null
}) {
  const fetcher = useCallback(
    () => stockService.salesHistory(ctx.tenantId, ctx.storeId, ctx.productCode),
    [ctx.tenantId, ctx.storeId, ctx.productCode],
  )
  const { data, isLoading, error, reload } = useStockResource(fetcher, panelKey(ctx))

  const sub = data && data.length > 0
    ? <span className="sa-panel-sub">{data.length} bills — click a row to see full bill</span>
    : undefined

  return (
    <SxCard>
      <SxCardHead title="Recent Sales" icon="bi-cart-check" sub={sub} />
      <SxCardBody flush>
        {isLoading ? (
          <div className="p-3"><TableSkeleton rows={5} columns={4} /></div>
        ) : error ? (
          <ErrorState description={error} onRetry={reload} />
        ) : !data || data.length === 0 ? (
          <EmptyState icon="bi-cart" title="No sales" description="No recent sales found." />
        ) : (
          <SxTable>
            <colgroup>
              <col style={{ width: '68px' }} />   {/* Date */}
              <col style={{ width: '74px' }} />   {/* Bill No */}
              <col />                              {/* Customer — flexible */}
              <col style={{ width: '40px' }} />   {/* Qty */}
            </colgroup>
            <thead>
              <tr>
                <th>Date</th>
                <th>Bill No.</th>
                <th>Customer</th>
                <th className="sx-num">Qty</th>
              </tr>
            </thead>
            <tbody>
              {data.map((row, i) => {
                const active = activeBillNo != null && row.bill_no === activeBillNo
                return (
                  <tr
                    key={`${row.bill_no}-${i}`}
                    className={`sa-rowsel${active ? ' sa-rowsel--on' : ''}`}
                    onClick={() => onSelect?.(row)}
                    title={`Bill ${row.bill_no} — ${row.customer ?? 'Unknown'} · Qty ${num(row.qty)}${row.discount ? ` · Disc ${num(row.discount)}%` : ''}`}
                  >
                    <td className="sx-dim">{date(row.date)}</td>
                    <td><span className="sa-bill-chip">{row.bill_no ?? '—'}</span></td>
                    <td className="sa-customer-cell">{row.customer ?? '—'}</td>
                    <td className="sx-num sa-qty-bold">{num(row.qty)}</td>
                  </tr>
                )
              })}
            </tbody>
          </SxTable>
        )}
      </SxCardBody>
    </SxCard>
  )
}

/* ---- Recent Purchases ----------------------------------------------------
   Columns: Date · GRN · Qty+Free · Cost
   4 cols — PTR/MRP/disc dropped to avoid cramping.
--------------------------------------------------------------------------- */

export function PurchasePanel({ ctx }: { ctx: ProductContext }) {
  const fetcher = useCallback(
    () => stockService.purchaseHistory(ctx.tenantId, ctx.storeId, ctx.productCode),
    [ctx.tenantId, ctx.storeId, ctx.productCode],
  )
  const { data, isLoading, error, reload } = useStockResource(fetcher, panelKey(ctx))

  const sub = data && data.length > 0
    ? <span className="sa-panel-sub">{data.length} GRNs</span>
    : undefined

  return (
    <SxCard>
      <SxCardHead title="Recent Purchases" icon="bi-truck" sub={sub} />
      <SxCardBody flush>
        {isLoading ? (
          <div className="p-3"><TableSkeleton rows={5} columns={4} /></div>
        ) : error ? (
          <ErrorState description={error} onRetry={reload} />
        ) : !data || data.length === 0 ? (
          <EmptyState icon="bi-truck" title="No purchases" description="No recent purchases found." />
        ) : (
          <SxTable>
            <colgroup>
              <col style={{ width: '68px' }} />   {/* Date */}
              <col style={{ width: '68px' }} />   {/* GRN */}
              <col style={{ width: '72px' }} />   {/* Qty+Free */}
              <col />                              {/* Cost — flexible */}
            </colgroup>
            <thead>
              <tr>
                <th>Date</th>
                <th>GRN</th>
                <th className="sx-num">Qty + Free</th>
                <th className="sx-num">Cost</th>
              </tr>
            </thead>
            <tbody>
              {data.map((row, i) => (
                <tr
                  key={`${row.grn_no}-${i}`}
                  title={`GRN ${row.grn_no} · Disc ${row.dis ?? 0}% · PTR ${money(row.ptr)} · MRP ${money(row.mrp)}`}
                >
                  <td className="sx-dim">{date(row.date)}</td>
                  <td><span className="sa-bill-chip sa-bill-chip--purch">{row.grn_no ?? '—'}</span></td>
                  <td className="sx-num">
                    <span className="sa-qty-pair">
                      <span className="sa-qty-bold">{num(row.qty)}</span>
                      {(row.free ?? 0) > 0 && (
                        <span className="sa-qty-pair__free">+{num(row.free)}</span>
                      )}
                    </span>
                  </td>
                  <td className="sx-num sa-cost-bold">{money(row.cost)}</td>
                </tr>
              ))}
            </tbody>
          </SxTable>
        )}
      </SxCardBody>
    </SxCard>
  )
}

/* ---- Bill Details --------------------------------------------------------
   Header strip: Bill No · Customer · Date · Total  (compact, always visible)
   Table: Product · Qty · Disc% · Amount   (4 cols — no # or Unit to save space)
   Current-product row is highlighted with an accent left-border.
--------------------------------------------------------------------------- */

export interface SelectedBill {
  billNo: string
  billDate: string | null
  customer: string | null
}

export function LatestBillPanel({ ctx, selected }: { ctx: ProductContext; selected?: SelectedBill | null }) {
  const salesFetcher = useCallback(
    () => stockService.salesHistory(ctx.tenantId, ctx.storeId, ctx.productCode),
    [ctx.tenantId, ctx.storeId, ctx.productCode],
  )
  const sales = useStockResource(salesFetcher, panelKey(ctx))
  const latest = sales.data?.[0] ?? null
  const eff: SelectedBill | null =
    selected ??
    (latest
      ? { billNo: latest.bill_no ?? '', billDate: latest.date ?? null, customer: latest.customer ?? null }
      : null)

  const effBillNo   = eff?.billNo ?? ''
  const effBillDate = eff?.billDate ?? ''
  const billKey     = effBillNo ? `${panelKey(ctx)}|${effBillNo}` : null
  const billFetcher = useCallback(
    () => stockService.billItems(ctx.tenantId, ctx.storeId, effBillNo, effBillDate),
    [ctx.tenantId, ctx.storeId, effBillNo, effBillDate],
  )
  const bill = useStockResource(billFetcher, billKey)

  const total     = (bill.data ?? []).reduce((s, r) => s + (r.amount ?? 0), 0)
  const itemCount = bill.data?.length ?? 0

  return (
    <SxCard className="sa-area--bill-card">
      <SxCardHead title="Bill Details" icon="bi-receipt" />
      <SxCardBody flush>

        {/* ── Bill header strip ── */}
        {eff && (
          <div className="sa-bill-strip">
            <div className="sa-bill-strip__meta">
              <span className="sa-bill-strip__no">{eff.billNo || '—'}</span>
              <span className="sa-bill-strip__cust">{eff.customer || '—'}</span>
              <span className="sa-bill-strip__date">{date(eff.billDate)}</span>
            </div>
            <div className="sa-bill-strip__total">
              <span className="sa-bill-strip__total-label">Bill Total</span>
              <span className="sa-bill-strip__total-val">{money(total)}</span>
              {itemCount > 0 && (
                <span className="sa-bill-strip__count">{itemCount} items</span>
              )}
            </div>
          </div>
        )}

        {/* ── Bill line items ── */}
        {sales.isLoading || bill.isLoading ? (
          <div className="p-3"><TableSkeleton rows={4} columns={4} /></div>
        ) : sales.error || bill.error ? (
          <ErrorState description={sales.error ?? bill.error ?? 'Failed to load bill'} onRetry={bill.reload} />
        ) : !eff ? (
          <EmptyState icon="bi-receipt" title="No bill selected" description="Click any sale row above to view its full bill." />
        ) : !bill.data || bill.data.length === 0 ? (
          <EmptyState icon="bi-receipt" title="No items" description="This bill has no line items." />
        ) : (
          <SxTable>
            <colgroup>
              <col />                              {/* Product — flexible */}
              <col style={{ width: '38px' }} />   {/* Qty */}
              <col style={{ width: '46px' }} />   {/* Disc% */}
              <col style={{ width: '72px' }} />   {/* Amount */}
            </colgroup>
            <thead>
              <tr>
                <th>Product</th>
                <th className="sx-num">Qty</th>
                <th className="sx-num">Disc%</th>
                <th className="sx-num">Amount</th>
              </tr>
            </thead>
            <tbody>
              {bill.data.map((row, i) => {
                const isCurrent =
                  row.product_name?.toLowerCase().trim() === ctx.productName?.toLowerCase().trim()
                return (
                  <tr key={i} className={isCurrent ? 'sa-bill-row--highlight' : ''}>
                    <td className={isCurrent ? 'sa-bill-product--active' : ''}>{row.product_name ?? '—'}</td>
                    <td className="sx-num sa-qty-bold">{num(row.qty)}</td>
                    <td className="sx-num">
                      {row.discount_pct != null && row.discount_pct > 0
                        ? <span className="sa-disc-pill">{num(row.discount_pct)}%</span>
                        : <span className="sx-dim">—</span>
                      }
                    </td>
                    <td className="sx-num sa-cost-bold">{money(row.amount)}</td>
                  </tr>
                )
              })}
            </tbody>
          </SxTable>
        )}
      </SxCardBody>
    </SxCard>
  )
}
