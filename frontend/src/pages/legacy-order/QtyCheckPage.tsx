import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { legacyOrderService } from '../../services/legacyOrderService'
import type {
  LegacyStore,
  MonthlyStatRow,
  OrderHistoryRow,
  OrderMode,
  PurchaseDetailRow,
  QtyCheckRow,
  SalesDetailRow,
} from '../../types/legacyOrder'
import './legacy-order.css'
import { FilterBar, FilterSelect, FilterTabs } from '../../design-system/components/FilterBar'

function fmtDate(value: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleDateString()
}

const CHART_SERIES: { key: keyof MonthlyStatRow; label: string; color: string }[] = [
  { key: 'PurchaseQuantity', label: 'Purchase', color: '#1d4ed8' },
  { key: 'SaleQuantity', label: 'Sales', color: '#15803d' },
  { key: 'StockInHand', label: 'Stock', color: '#dc2626' },
  { key: 'AdjustmentQuantity', label: 'Adjustment', color: '#f59e0b' },
  { key: 'TransferInQuantity', label: 'TIN', color: '#0ea5e9' },
  { key: 'TransferOutQuantity', label: 'TOUT', color: '#a855f7' },
]

function MonthlyStatsChart({ rows }: { rows: MonthlyStatRow[] }) {
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

export default function QtyCheckPage() {
  const [stores, setStores] = useState<LegacyStore[]>([])
  const [store, setStore] = useState('')
  const [mode, setMode] = useState<OrderMode>('local')
  const [rows, setRows] = useState<QtyCheckRow[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [edits, setEdits] = useState<Record<number, number>>({})
  const [saving, setSaving] = useState<number | null>(null)

  const [purchaseDetails, setPurchaseDetails] = useState<PurchaseDetailRow[]>([])
  const [salesDetails, setSalesDetails] = useState<SalesDetailRow[]>([])
  const [monthlyStats, setMonthlyStats] = useState<MonthlyStatRow[]>([])
  const [orderHistory, setOrderHistory] = useState<OrderHistoryRow[]>([])
  const [detailLoading, setDetailLoading] = useState(false)

  const inputRefs = useRef<Array<HTMLInputElement | null>>([])

  useEffect(() => {
    legacyOrderService.listStores()
      .then((list) => {
        setStores(list)
        if (list.length) setStore(list[0].store_name)
      })
      .catch((e: Error) => setError(e.message))
  }, [])

  const loadRows = useCallback((storeName: string) => {
    if (!storeName) return
    setLoading(true)
    setEdits({})
    setSelectedIndex(0)
    legacyOrderService.qtyCheckRows(storeName)
      .then(setRows)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    loadRows(store)
  }, [store, loadRows])

  const selectedRow = rows[selectedIndex]

  useEffect(() => {
    if (!store || !selectedRow) {
      setPurchaseDetails([])
      setSalesDetails([])
      setMonthlyStats([])
      setOrderHistory([])
      return
    }
    setDetailLoading(true)
    const productCode = selectedRow.productcode
    Promise.all([
      legacyOrderService.qtyCheckPurchaseDetails(store, productCode, mode),
      legacyOrderService.qtyCheckSalesDetails(store, productCode, mode),
      legacyOrderService.qtyCheckMonthlyStats(store, productCode, mode),
      legacyOrderService.qtyCheckOrderHistory(store, productCode),
    ])
      .then(([purchase, sales, stats, history]) => {
        setPurchaseDetails(purchase)
        setSalesDetails(sales)
        setMonthlyStats(stats)
        setOrderHistory(history)
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setDetailLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [store, mode, selectedRow?.productcode])

  const commit = useCallback((index: number, value: number) => {
    const row = rows[index]
    if (!row || !store) return
    setSaving(row.productcode)
    legacyOrderService.updateQtyCheck(store, row.productcode, value)
      .then(() => {
        setRows((current) => current.filter((r) => r.productcode !== row.productcode))
        setEdits((current) => {
          const next = { ...current }
          delete next[row.productcode]
          return next
        })
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setSaving(null))
  }, [rows, store])

  useEffect(() => {
    setSelectedIndex((current) => Math.min(current, Math.max(0, rows.length - 1)))
  }, [rows.length])

  const focusRow = (index: number) => {
    const clamped = Math.max(0, Math.min(rows.length - 1, index))
    setSelectedIndex(clamped)
    requestAnimationFrame(() => inputRefs.current[clamped]?.focus())
  }

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>, index: number) => {
    const row = rows[index]
    if (!row) return
    if (e.key === 'Enter') {
      e.preventDefault()
      const value = edits[row.productcode] ?? row.orderqty
      commit(index, value)
    } else if (e.key === 'Escape') {
      e.preventDefault()
      commit(index, 0)
    } else if (e.key === 'ArrowDown') {
      e.preventDefault()
      focusRow(index + 1)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      focusRow(index - 1)
    }
  }

  const totalProducts = rows.length

  return (
    <div className="legacy-order qc-shell">
      <header className="lo-header">
        <div>
          <h1>Order Management · Qty Check</h1>
          <p className="lo-sub">Review products flagged for quantity check. Enter saves the typed quantity, Escape zeroes it out ("no need") — both close the row out immediately, matching the legacy VB.NET grid.</p>
        </div>
        <Link to="/legacy-order" className="lo-btn"><i className="bi bi-arrow-left" /> Back to Legacy Order</Link>
      </header>

      {error && <div className="lo-error" role="alert">{error}<button type="button" onClick={() => setError(null)} aria-label="Dismiss">×</button></div>}

      <section className="lo-card">
        <div className="lo-section-title">
          <FilterBar compact className="lo-row" ariaLabel="Quantity check filters">
            <FilterSelect label="Select Store" ariaLabel="Select Store" value={store} onChange={setStore}>
              {stores.map((s) => <option key={s.store_name} value={s.store_name}>{s.store_name}</option>)}
            </FilterSelect>
            <FilterTabs
              value={mode}
              ariaLabel="Database source"
              options={[{ value: 'local', label: 'Local DB' }, { value: 'remote', label: 'Remote DB' }]}
              onChange={setMode}
            />
          </FilterBar>
          <span className="lo-count">{totalProducts} products</span>
        </div>
      </section>

      <div className="lo-lower-grid">
        <section className="lo-card">
          <h2>Qty Check grid</h2>
          <div className="lo-scroll">
            <table className="lo-table">
              <thead>
                <tr><th>#</th><th>Product Name</th><th className="lo-num">Or Qty</th><th className="lo-num">Stock</th><th className="lo-num">Pack</th><th>Desc</th><th className="lo-num">Sls Qty</th><th className="lo-num">MRP</th><th>LR Date</th><th>LS Date</th><th className="lo-num">Max Qty</th><th>Txn Date</th><th>Wanted</th></tr>
              </thead>
              <tbody>
                {rows.map((row, index) => {
                  const value = edits[row.productcode] ?? row.orderqty
                  const isSelected = index === selectedIndex
                  return (
                    <tr
                      key={row.productcode}
                      className={isSelected ? 'lo-supplier-row is-selected' : undefined}
                      onClick={() => focusRow(index)}
                    >
                      <td>{index + 1}</td>
                      <td><span className="qc-product-name" title={row.productname}>{row.productname}</span></td>
                      <td className="lo-num">
                        <input
                          ref={(el) => { inputRefs.current[index] = el }}
                          type="number"
                          min={0}
                          aria-label={`${row.productname} order quantity`}
                          value={value}
                          disabled={saving === row.productcode}
                          onFocus={() => setSelectedIndex(index)}
                          onChange={(e) => setEdits((current) => ({ ...current, [row.productcode]: Number(e.target.value) }))}
                          onKeyDown={(e) => onKeyDown(e, index)}
                          style={{ width: '4rem' }}
                        />
                      </td>
                      <td className="lo-num">{row.totalstock}</td>
                      <td className="lo-num">{row.saleunit}</td>
                      <td>{row.unitdescription}</td>
                      <td className="lo-num">{row.slsqty}</td>
                      <td className="lo-num">{row.mrp?.toFixed?.(2) ?? row.mrp}</td>
                      <td>{fmtDate(row.lastreceiveddate)}</td>
                      <td>{fmtDate(row.lastsaledate)}</td>
                      <td className="lo-num">{row.maxsaleqty}</td>
                      <td>{fmtDate(row.Transactiondate)}</td>
                      <td>{row.wantedtype ?? '—'}</td>
                    </tr>
                  )
                })}
                {!rows.length && <tr><td colSpan={13} className="lo-empty">{loading ? 'Loading Qty Check grid…' : 'Nothing left to review for this store.'}</td></tr>}
              </tbody>
            </table>
          </div>
        </section>

        <section className="lo-card lo-activity">
          <h2>Product detail</h2>
          {!selectedRow && <div className="lo-empty">Select a product to see stock, sales and chart detail.</div>}
          {selectedRow && (
            <div className="qc-detail-scroll">
              <p className="lo-note">{selectedRow.productname} · {selectedRow.productcode}{detailLoading ? ' · loading…' : ''}</p>

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
          )}
        </section>
      </div>

      <section className="lo-card qc-history">
        <h2>Order history</h2>
        <p className="lo-note">Last 25 previous-order entries for the selected product (OrderManagementBackup).</p>
        <div className="lo-scroll">
          <table className="lo-table">
            <thead><tr><th>Product Name</th><th className="lo-num">Or Qty</th><th className="lo-num">Org Order</th><th className="lo-num">Pack</th><th className="lo-num">MRP</th><th>Remarks</th><th>Wanted Date</th><th>Wanted</th><th>Or Supplier</th></tr></thead>
            <tbody>
              {orderHistory.map((row, i) => (
                <tr key={i}><td><span className="qc-product-name" title={row.ProductName}>{row.ProductName}</span></td><td className="lo-num">{row.Orqty ?? '—'}</td><td className="lo-num">{row.OrgOrderQty ?? '—'}</td><td className="lo-num">{row.saleunit ?? '—'}</td><td className="lo-num">{row.MRP ?? '—'}</td><td>{row.remarks ?? '—'}</td><td>{fmtDate(row.Wanteddate)}</td><td>{row.WantedType ?? '—'}</td><td>{row.Orsupplier ?? '—'}</td></tr>
              ))}
              {!orderHistory.length && <tr><td colSpan={9} className="lo-empty">{selectedRow ? 'No previous-order history for this product.' : 'Select a product above to see its history.'}</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
