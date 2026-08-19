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
  const padL = 30
  const padB = 20
  const plotW = W - padL - 10
  const plotH = H - padB - 10
  const groupW = plotW / rows.length
  const barW = Math.max(3, (groupW * 0.8) / CHART_SERIES.length)

  return (
    <div>
      <svg width="100%" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Monthly statistics chart">
        {rows.map((row, i) => {
          const groupX = padL + i * groupW + groupW * 0.1
          return (
            <g key={row.MonthOfStatistics}>
              {CHART_SERIES.map((series, j) => {
                const value = Number(row[series.key]) || 0
                const h = (value / max) * plotH
                const x = groupX + j * barW
                const y = padB + (plotH - h)
                return <rect key={series.key} x={x} y={y} width={barW - 1} height={h} fill={series.color}><title>{`${series.label}: ${value}`}</title></rect>
              })}
              <text x={groupX + (barW * CHART_SERIES.length) / 2} y={H - 4} textAnchor="middle" fontSize="9" fill="currentColor">{row.MonthOfStatistics}</text>
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
  productName?: string
  mode: OrderMode
  onError?: (message: string) => void
}

/** Shared product detail: purchase/GRN history, bill/sales history and the
 *  monthly-statistics chart. Ports RetrieveDataForPurchaseDetails/SalesDetails/
 *  Chart. Self-fetches so both the Qty-Check screen and the Order Workspace can
 *  drop it in. Order history (OrderManagementBackup) is intentionally left to
 *  the host page, which renders it in its own full-width section. */
export function ProductDetailPanel({ store, productCode, productName, mode, onError }: ProductDetailPanelProps) {
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
      <p className="lo-note">{productName ?? ''} · {productCode}{loading ? ' · loading…' : ''}</p>

      <h3 style={{ fontSize: '0.82rem', margin: '0.6rem 0 0.3rem' }}>Purchase / GRN history</h3>
      <div className="lo-scroll" style={{ maxHeight: '9rem' }}>
        <table className="lo-table">
          <thead><tr><th className="lo-num">Stock</th><th className="lo-num">Free</th><th className="lo-num">Dis</th><th className="lo-num">Cost</th><th className="lo-num">PTR</th><th className="lo-num">MRP</th><th>GRN Date</th><th>Supplier</th></tr></thead>
          <tbody>
            {purchaseDetails.map((row, i) => (
              <tr key={i}><td className="lo-num">{row.RStock ?? '—'}</td><td className="lo-num">{row.FreeQty ?? '—'}</td><td className="lo-num">{row.DIS ?? '—'}</td><td className="lo-num">{row.ItemCost ?? '—'}</td><td className="lo-num">{row.PTR ?? '—'}</td><td className="lo-num">{row.MRP ?? '—'}</td><td>{fmtDate(row.GRNDate)}</td><td>{row.SupplierName ?? '—'}</td></tr>
            ))}
            {!purchaseDetails.length && <tr><td colSpan={8} className="lo-empty">No purchase history.</td></tr>}
          </tbody>
        </table>
      </div>

      <h3 style={{ fontSize: '0.82rem', margin: '0.6rem 0 0.3rem' }}>Bill / sales history</h3>
      <div className="lo-scroll" style={{ maxHeight: '9rem' }}>
        <table className="lo-table">
          <thead><tr><th className="lo-num">Qty</th><th>Bill Time</th><th>Salesman</th><th>Customer</th><th className="lo-num">Dis</th><th>Type</th><th className="lo-num">MRP</th></tr></thead>
          <tbody>
            {salesDetails.map((row, i) => (
              <tr key={i}><td className="lo-num">{row.TotalQuantity ?? '—'}</td><td>{fmtDate(row.Bill_Time)}</td><td>{row.Salesmanname ?? '—'}</td><td>{row.CUSTOMERNAME ?? '—'}</td><td className="lo-num">{row.dis ?? '—'}</td><td>{row.type ?? '—'}</td><td className="lo-num">{row.mrp ?? '—'}</td></tr>
            ))}
            {!salesDetails.length && <tr><td colSpan={7} className="lo-empty">No sales history.</td></tr>}
          </tbody>
        </table>
      </div>

      <h3 style={{ fontSize: '0.82rem', margin: '0.6rem 0 0.3rem' }}>Monthly statistics</h3>
      <MonthlyStatsChart rows={monthlyStats} />
    </div>
  )
}
