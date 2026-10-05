import { useEffect, useState } from 'react'
import { legacyOrderService } from '../../services/legacyOrderService'
import type {
  MonthlyStatRow,
  OrderMode,
  PurchaseDetailRow,
  SalesDetailRow,
} from '../../types/legacyOrder'
import { fmtDate } from './format'

const BAR_SERIES: { key: 'total_in' | 'total_out' | 'adjustment'; label: string; cls: string }[] = [
  { key: 'total_in', label: 'In', cls: 'in' },
  { key: 'total_out', label: 'Out', cls: 'out' },
  { key: 'adjustment', label: 'Adjustment', cls: 'adj' },
]

function fmtMonth(ym: string) {
  const [y, m] = ym.split('-')
  const d = new Date(Number(y), Number(m) - 1, 1)
  return d.toLocaleDateString(undefined, { month: 'short', year: '2-digit' })
}

/** Modern stock-movement chart: grouped IN/OUT/ADJUSTMENT columns + a STOCK
 *  line, sharing one linear axis (never a second scale). The underlying
 *  quantities are the POS's own net/signed monthly rollup -- IN/OUT already
 *  exclude returns from double counting; see repository.qty_check_monthly_stats
 *  for the verified reconciliation. Hovering a month reveals the breakdown
 *  (gross sales, sales/expiry return, raw adjustment) behind the net figures. */
export function MonthlyStatsChart({ rows }: { rows: MonthlyStatRow[] }) {
  const [hover, setHover] = useState<number | null>(null)
  if (!rows.length) return <div className="lo-empty">No monthly statistics for this product.</div>

  const allValues = rows.flatMap((r) => [r.total_in, r.total_out, r.adjustment, r.stock])
  const max = Math.max(1, ...allValues)
  const min = Math.min(0, ...allValues)
  const span = max - min || 1
  const zeroPct = (max / span) * 100 // baseline position from the top, in %

  const stockPoints = rows
    .map((row, i) => `${((i + 0.5) / rows.length) * 100},${((max - row.stock) / span) * 100}`)
    .join(' ')

  return (
    <div className="qc-chart">
      <div className="qc-chart__plot" role="img" aria-label="Monthly stock movement chart">
        <div className="qc-chart__zero" style={{ top: `${zeroPct}%` }} />
        <svg className="qc-chart__stockline" viewBox="0 0 100 100" preserveAspectRatio="none">
          <polyline points={stockPoints} vectorEffect="non-scaling-stroke" />
        </svg>
        {rows.map((row, i) => {
          const stockPct = ((max - row.stock) / span) * 100
          return (
            <div
              key={`${row.month}-${i}`}
              className={`qc-chart__group${hover === i ? ' is-hover' : ''}`}
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover((h) => (h === i ? null : h))}
            >
              <div className="qc-chart__bars">
                {BAR_SERIES.map((series) => {
                  const value = row[series.key]
                  const topPct = value >= 0 ? ((max - value) / span) * 100 : zeroPct
                  const heightPct = (Math.abs(value) / span) * 100
                  return (
                    <div key={series.key} className="qc-chart__col">
                      <div
                        className={`qc-chart__bar qc-chart__bar--${series.cls}`}
                        style={{ top: `${topPct}%`, height: `${heightPct}%` }}
                      >
                        {value !== 0 && (
                          <span className={`qc-chart__val${value < 0 ? ' qc-chart__val--below' : ''}`}>
                            {value > 0 ? `+${value}` : value}
                          </span>
                        )}
                      </div>
                    </div>
                  )
                })}
                <div className="qc-chart__stock-dot" style={{ top: `${stockPct}%` }}>
                  <span className="qc-chart__val qc-chart__val--stock">{row.stock}</span>
                </div>
              </div>
              <div className="qc-chart__month">{fmtMonth(row.month)}</div>

              {hover === i && (
                <div className="qc-chart__tooltip">
                  <div className="qc-chart__tt-title">{fmtMonth(row.month)}</div>
                  <div className="qc-chart__tt-row qc-chart__tt-head qc-chart__tt-in">
                    <span>In</span><b>{row.total_in}</b>
                  </div>
                  <div className="qc-chart__tt-sub">
                    <span>Purchase</span><span>{row.purchase}</span>
                  </div>
                  <div className="qc-chart__tt-sub">
                    <span>Transfer in</span><span>{row.transfer_in}</span>
                  </div>

                  <div className="qc-chart__tt-row qc-chart__tt-head qc-chart__tt-out">
                    <span>Out</span><b>{row.total_out}</b>
                  </div>
                  <div className="qc-chart__tt-sub">
                    <span>Sales (net)</span><span>{row.sales}</span>
                  </div>
                  {row.sales_return > 0 && (
                    <div className="qc-chart__tt-sub qc-chart__tt-note">
                      <span>&nbsp;&nbsp;of which gross sales</span><span>{row.gross_sales}</span>
                    </div>
                  )}
                  {row.sales_return > 0 && (
                    <div className="qc-chart__tt-sub qc-chart__tt-note">
                      <span>&nbsp;&nbsp;less sales return</span><span>-{row.sales_return}</span>
                    </div>
                  )}
                  <div className="qc-chart__tt-sub">
                    <span>Transfer out</span><span>{row.transfer_out}</span>
                  </div>

                  <div className="qc-chart__tt-row qc-chart__tt-head qc-chart__tt-adj">
                    <span>Adjustment</span><b>{row.adjustment > 0 ? `+${row.adjustment}` : row.adjustment}</b>
                  </div>
                  {row.expiry_return > 0 && (
                    <>
                      <div className="qc-chart__tt-sub qc-chart__tt-note">
                        <span>&nbsp;&nbsp;stock adjustment</span><span>{row.stock_adjustment}</span>
                      </div>
                      <div className="qc-chart__tt-sub qc-chart__tt-note">
                        <span>&nbsp;&nbsp;expiry return</span><span>-{row.expiry_return}</span>
                      </div>
                    </>
                  )}

                  <div className="qc-chart__tt-row qc-chart__tt-head qc-chart__tt-stock">
                    <span>Stock</span><b>{row.stock}</b>
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
      <div className="qc-chart__legend">
        <span className="qc-chart__leg"><i className="qc-chart__sw qc-chart__sw--in" />In</span>
        <span className="qc-chart__leg"><i className="qc-chart__sw qc-chart__sw--out" />Out</span>
        <span className="qc-chart__leg"><i className="qc-chart__sw qc-chart__sw--adj" />Adjustment</span>
        <span className="qc-chart__leg"><i className="qc-chart__sw qc-chart__sw--stock-line" />Stock</span>
      </div>
    </div>
  )
}

interface ProductDetailPanelProps {
  store: string
  productCode: number | null
  mode: OrderMode
  onError?: (message: string) => void
}

/** Shared product detail: purchase/GRN history, bill/sales history and the
 *  monthly-statistics chart. Ports RetrieveDataForPurchaseDetails/SalesDetails/
 *  Chart. Self-fetches so both the Qty-Check screen and the Order Workspace can
 *  drop it in. Order history (OrderManagementBackup) is intentionally left to
 *  the host page, which renders it in its own full-width section. */
export function ProductDetailPanel({ store, productCode, mode, onError }: ProductDetailPanelProps) {
  const [purchaseDetails, setPurchaseDetails] = useState<PurchaseDetailRow[]>([])
  const [salesDetails, setSalesDetails] = useState<SalesDetailRow[]>([])
  const [monthlyStats, setMonthlyStats] = useState<MonthlyStatRow[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!store || productCode == null) {
      setPurchaseDetails([])
      setSalesDetails([])
      setMonthlyStats([])
      return
    }
    let cancelled = false
    setLoading(true)
    Promise.all([
      legacyOrderService.qtyCheckPurchaseDetails(store, productCode, mode),
      legacyOrderService.qtyCheckSalesDetails(store, productCode, mode),
      legacyOrderService.qtyCheckMonthlyStats(store, productCode, mode),
    ])
      .then(([purchase, sales, stats]) => {
        if (cancelled) return
        setPurchaseDetails(purchase)
        setSalesDetails(sales)
        setMonthlyStats(stats)
      })
      .catch((e: Error) => { if (!cancelled) onError?.(e.message) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [store, mode, productCode])

  if (productCode == null) {
    return <div className="lo-empty">Select a product to see stock, sales and chart detail.</div>
  }

  return (
    <div className="qc-detail-scroll">
      {loading && <p className="lo-note qc-pi-head">Loading…</p>}

      <section className="qc-pi-section qc-pi-grow">
        <h3 className="qc-pi-title">Purchase / GRN history</h3>
        <div className="lo-scroll qc-pi-scroll">
          <table className="lo-table lo-table--pi">
            <thead><tr><th className="lo-num">Stock</th><th className="lo-num">Free</th><th className="lo-num">Dis</th><th className="lo-num">Cost</th><th className="lo-num">PTR</th><th className="lo-num">MRP</th><th>GRN Date</th><th>Supplier</th></tr></thead>
            <tbody>
              {purchaseDetails.map((row, i) => {
                // Legacy: rows that came with free goods (free > 0) are highlighted.
                const free = Number(row.FreeQty) || 0
                return (
                <tr key={i} className={free > 0 ? 'qc-pi-freerow' : undefined}><td className="lo-num">{row.RStock ?? '—'}</td><td className={`lo-num${free > 0 ? ' qc-pi-free' : ''}`}>{row.FreeQty ?? '—'}</td><td className="lo-num">{row.DIS ?? '—'}</td><td className="lo-num">{row.ItemCost ?? '—'}</td><td className="lo-num">{row.PTR ?? '—'}</td><td className="lo-num">{row.MRP ?? '—'}</td><td>{fmtDate(row.GRNDate)}</td><td>{row.SupplierName ?? '—'}</td></tr>
                )
              })}
              {!purchaseDetails.length && <tr><td colSpan={8} className="lo-empty">No purchase history.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      <section className="qc-pi-section qc-pi-grow">
        <h3 className="qc-pi-title">Bill / sales history</h3>
        <div className="lo-scroll qc-pi-scroll">
          <table className="lo-table lo-table--pi">
            <thead><tr><th className="lo-num">Qty</th><th>Bill Time</th><th>Salesman</th><th>Customer</th><th className="lo-num">Dis</th><th>Type</th><th className="lo-num">MRP</th></tr></thead>
            <tbody>
              {salesDetails.map((row, i) => (
                <tr key={i}><td className="lo-num">{row.TotalQuantity ?? '—'}</td><td>{fmtDate(row.Bill_Time)}</td><td>{row.Salesmanname ?? '—'}</td><td>{row.CUSTOMERNAME ?? '—'}</td><td className="lo-num">{row.dis ?? '—'}</td><td>{row.type ?? '—'}</td><td className="lo-num">{row.mrp ?? '—'}</td></tr>
              ))}
              {!salesDetails.length && <tr><td colSpan={7} className="lo-empty">No sales history.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      <section className="qc-pi-section qc-pi-chart">
        <h3 className="qc-pi-title">Monthly statistics</h3>
        <MonthlyStatsChart rows={monthlyStats} />
      </section>
    </div>
  )
}
