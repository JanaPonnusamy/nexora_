import { useEffect, useState } from 'react'
import { legacyOrderService } from '../../services/legacyOrderService'
import type {
  MonthlyStatRow,
  OrderMode,
  PurchaseDetailRow,
  SalesDetailRow,
} from '../../types/legacyOrder'
import { fmtDate } from './format'

const CHART_SERIES: { key: keyof MonthlyStatRow; label: string; color: string }[] = [
  { key: 'PurchaseQuantity', label: 'Purchase', color: '#1d4ed8' },
  { key: 'SaleQuantity', label: 'Sales', color: '#15803d' },
  { key: 'StockInHand', label: 'Stock', color: '#dc2626' },
  { key: 'AdjustmentQuantity', label: 'Adjustment', color: '#f59e0b' },
  { key: 'TransferInQuantity', label: 'TIN', color: '#0ea5e9' },
  { key: 'TransferOutQuantity', label: 'TOUT', color: '#a855f7' },
]

/** Port of the VB Chart1 grouped-bar chart: last 3 months of ProductTrans. */
export function MonthlyStatsChart({ rows }: { rows: MonthlyStatRow[] }) {
  if (!rows.length) return <div className="lo-empty">No monthly statistics for this product.</div>
  const max = Math.max(1, ...rows.flatMap((row) => CHART_SERIES.map((s) => Number(row[s.key]) || 0)))
  const W = 560
  const H = 200
  const padL = 34
  const padR = 8
  const padT = 8
  const padB = 22
  const plotW = W - padL - padR
  const plotH = H - padT - padB
  const baseY = padT + plotH
  const groupW = plotW / rows.length
  // Bars fill 80% of each group's slot (10% gap each side); dividing that inner
  // width evenly across the series guarantees the bars can never spill past the
  // group and overlap the neighbouring month — the old Math.max(3, …) floor
  // could, which is what made the bars overlap.
  const groupInner = groupW * 0.8
  const groupPad = (groupW - groupInner) / 2
  const barW = groupInner / CHART_SERIES.length

  return (
    <div>
      <svg width="100%" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet" role="img" aria-label="Monthly statistics chart">
        <line x1={padL} y1={baseY} x2={W - padR} y2={baseY} stroke="currentColor" strokeOpacity="0.25" />
        {rows.map((row, i) => {
          const groupX = padL + i * groupW + groupPad
          return (
            <g key={`${row.MonthOfStatistics}-${i}`}>
              {CHART_SERIES.map((series, j) => {
                const value = Number(row[series.key]) || 0
                // Negative values (e.g. stock/adjustment corrections) would make
                // a negative <rect height>, which is invalid SVG — clamp to 0.
                const h = Math.max(0, (value / max) * plotH)
                const x = groupX + j * barW
                const y = baseY - h
                return <rect key={series.key} x={x} y={y} width={Math.max(1, barW - 0.75)} height={h} fill={series.color}><title>{`${series.label}: ${value}`}</title></rect>
              })}
              <text x={groupX + groupInner / 2} y={H - 6} textAnchor="middle" fontSize="9" fill="currentColor">{row.MonthOfStatistics}</text>
            </g>
          )
        })}
      </svg>
      <div className="lo-actions" style={{ flexWrap: 'wrap', marginTop: '0.4rem' }}>
        {CHART_SERIES.map((series) => (
          <span key={series.key} style={{ display: 'inline-flex', alignItems: 'center', gap: '0.3rem', fontSize: '0.7rem' }}>
            <span style={{ width: '0.6rem', height: '0.6rem', background: series.color, borderRadius: '2px', display: 'inline-block' }} />
            {series.label}
          </span>
        ))}
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
            <thead><tr><th className="lo-num">Stock</th><th className="lo-num qc-pi-free">Free</th><th className="lo-num">Dis</th><th className="lo-num">Cost</th><th className="lo-num">PTR</th><th className="lo-num">MRP</th><th>GRN Date</th><th>Supplier</th></tr></thead>
            <tbody>
              {purchaseDetails.map((row, i) => (
                <tr key={i}><td className="lo-num">{row.RStock ?? '—'}</td><td className="lo-num qc-pi-free">{row.FreeQty ?? '—'}</td><td className="lo-num">{row.DIS ?? '—'}</td><td className="lo-num">{row.ItemCost ?? '—'}</td><td className="lo-num">{row.PTR ?? '—'}</td><td className="lo-num">{row.MRP ?? '—'}</td><td>{fmtDate(row.GRNDate)}</td><td>{row.SupplierName ?? '—'}</td></tr>
              ))}
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
