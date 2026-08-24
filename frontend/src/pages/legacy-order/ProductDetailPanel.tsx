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

/** Port of the VB Chart1 grouped-bar chart: last 3 months of ProductTrans.
 *  Rendered as HTML/flex bars (not SVG) so it fills the panel width with no
 *  letterbox gaps, shows each value, and takes a light card + glossy bars. */
export function MonthlyStatsChart({ rows }: { rows: MonthlyStatRow[] }) {
  if (!rows.length) return <div className="lo-empty">No monthly statistics for this product.</div>
  const max = Math.max(1, ...rows.flatMap((row) => CHART_SERIES.map((s) => Number(row[s.key]) || 0)))

  return (
    <div className="qc-chart">
      <div className="qc-chart__plot" role="img" aria-label="Monthly statistics chart">
        {rows.map((row, i) => (
          <div className="qc-chart__group" key={`${row.MonthOfStatistics}-${i}`}>
            <div className="qc-chart__bars">
              {CHART_SERIES.map((series) => {
                const value = Number(row[series.key]) || 0
                const pct = Math.max(0, Math.min(100, (value / max) * 100))
                return (
                  <div
                    key={series.key}
                    className="qc-chart__bar"
                    style={{ height: `${pct}%`, background: series.color }}
                    title={`${series.label}: ${value}`}
                  >
                    {value !== 0 && <span className="qc-chart__val">{value}</span>}
                  </div>
                )
              })}
            </div>
            <div className="qc-chart__month">{row.MonthOfStatistics}</div>
          </div>
        ))}
      </div>
      <div className="qc-chart__legend">
        {CHART_SERIES.map((series) => (
          <span key={series.key} className="qc-chart__leg">
            <i style={{ background: series.color }} />{series.label}
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
