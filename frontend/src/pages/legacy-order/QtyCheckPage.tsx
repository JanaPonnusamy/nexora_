import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { legacyOrderService } from '../../services/legacyOrderService'
import type {
  LegacyStore,
  OrderHistoryRow,
  OrderMode,
  QtyCheckRow,
} from '../../types/legacyOrder'
import './legacy-order.css'
import { FilterBar, FilterSelect, FilterTabs } from '../../design-system/components/FilterBar'
import { ProductDetailPanel } from './ProductDetailPanel'
import { fmtDate } from './format'

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

  const [orderHistory, setOrderHistory] = useState<OrderHistoryRow[]>([])

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
      setOrderHistory([])
      return
    }
    legacyOrderService.qtyCheckOrderHistory(store, selectedRow.productcode)
      .then(setOrderHistory)
      .catch((e: Error) => setError(e.message))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [store, selectedRow?.productcode])

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
        <div className="lo-actions">
          <Link to="/legacy-order/workspace" className="lo-btn"><i className="bi bi-grid-3x3-gap" /> Order Workspace</Link>
          <Link to="/legacy-order" className="lo-btn"><i className="bi bi-arrow-left" /> Back to Legacy Order</Link>
        </div>
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
          <ProductDetailPanel
            store={store}
            productCode={selectedRow?.productcode ?? null}
            productName={selectedRow?.productname}
            mode={mode}
            onError={setError}
          />
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
