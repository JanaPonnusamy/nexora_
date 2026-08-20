import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { legacyOrderService } from '../../services/legacyOrderService'
import type {
  LegacyStore,
  OrderHistoryRow,
  OrderMode,
  QtyCheckRow,
} from '../../types/legacyOrder'
import './legacy-order.css'
import { FilterBar, FilterSearch, FilterSelect, FilterTabs } from '../../design-system/components/FilterBar'
import { ProductDetailPanel } from './ProductDetailPanel'
import { OrderWorkflowPanel } from './OrderWorkflowPanel'
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
  const [search, setSearch] = useState('')
  const [productType, setProductType] = useState('All')
  const [wantedType, setWantedType] = useState('All')
  const [workflowRefresh, setWorkflowRefresh] = useState(0)

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
    const handle = window.setTimeout(() => loadRows(store), 0)
    return () => window.clearTimeout(handle)
  }, [store, loadRows])

  const wantedTypes = useMemo(() => Array.from(new Set(rows.map((row) => row.wantedtype).filter(Boolean) as string[])).sort(), [rows])
  const filteredRows = useMemo(() => {
    const term = search.trim().toLowerCase()
    return rows.filter((row) => (
      (!term || row.productname.toLowerCase().includes(term) || String(row.productcode).includes(term))
      && (productType === 'All' || row.producttypename === productType)
      && (wantedType === 'All' || row.wantedtype === wantedType)
    ))
  }, [rows, search, productType, wantedType])

  const effectiveSelectedIndex = Math.min(selectedIndex, Math.max(0, filteredRows.length - 1))
  const selectedRow = filteredRows[effectiveSelectedIndex]

  useEffect(() => {
    if (!store || !selectedRow) {
      return
    }
    legacyOrderService.qtyCheckOrderHistory(store, selectedRow.productcode)
      .then(setOrderHistory)
      .catch((e: Error) => setError(e.message))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [store, selectedRow?.productcode])

  const commit = useCallback((row: QtyCheckRow, value: number) => {
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
      .finally(() => { setSaving(null); setWorkflowRefresh((current) => current + 1) })
  }, [store])

  const focusRow = (index: number) => {
    const clamped = Math.max(0, Math.min(filteredRows.length - 1, index))
    setSelectedIndex(clamped)
    requestAnimationFrame(() => inputRefs.current[clamped]?.focus())
  }

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>, index: number) => {
    const row = filteredRows[index]
    if (!row) return
    if (e.key === 'Enter') {
      e.preventDefault()
      const value = edits[row.productcode] ?? row.orderqty
      commit(row, value)
    } else if (e.key === 'Escape') {
      e.preventDefault()
      commit(row, 0)
    } else if (e.key === 'ArrowDown') {
      e.preventDefault()
      focusRow(index + 1)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      focusRow(index - 1)
    }
  }

  const totalProducts = filteredRows.length
  const hasFilters = Boolean(search.trim()) || productType !== 'All' || wantedType !== 'All'

  const resetFilters = () => {
    setSearch('')
    setProductType('All')
    setWantedType('All')
  }

  return (
    <div className="legacy-order qc-shell">
      <header className="lo-header">
        <div>
          <h1>Order Management · Qty Check</h1>
          <p className="lo-sub">Confirm demand one product at a time. Enter accepts the quantity; Escape marks the line as no need and advances.</p>
        </div>
        <div className="lo-actions">
          <Link to="/legacy-order/workspace" className="lo-btn"><i className="bi bi-grid-3x3-gap" /> Order Workspace</Link>
          <Link to="/legacy-order" className="lo-btn"><i className="bi bi-arrow-left" /> Back to Legacy Order</Link>
        </div>
      </header>

      {error && <div className="lo-error" role="alert">{error}<button type="button" onClick={() => setError(null)} aria-label="Dismiss">×</button></div>}

      <OrderWorkflowPanel store={store} refreshToken={workflowRefresh} onError={setError} />

      <section className="lo-card lo-filter-card qc-filter-panel">
        <div className="lo-section-title">
          <FilterBar compact className="lo-row" ariaLabel="Quantity check filters">
            <FilterSelect label="Store" ariaLabel="Select Store" value={store} onChange={setStore}>
              {stores.map((s) => <option key={s.store_name} value={s.store_name}>{s.store_name}</option>)}
            </FilterSelect>
            <FilterTabs
              value={mode}
              ariaLabel="Database source"
              options={[{ value: 'local', label: 'Local DB' }, { value: 'remote', label: 'Remote DB' }]}
              onChange={setMode}
            />
            <FilterSearch className="qc-product-search" value={search} placeholder="Search product or code…" ariaLabel="Search quantity-check products" onChange={setSearch} />
            <FilterSelect label="Product type" ariaLabel="Product type" value={productType} onChange={setProductType}>
              <option value="All">All products</option>
              <option value="Pharma">Pharma</option>
              <option value="Non Pharma">Non Pharma</option>
            </FilterSelect>
            <FilterSelect label="Wanted reason" ariaLabel="Wanted reason" value={wantedType} onChange={setWantedType}>
              <option value="All">All reasons</option>
              {wantedTypes.map((value) => <option key={value} value={value}>{value}</option>)}
            </FilterSelect>
          </FilterBar>
          <div className="qc-queue-count" aria-label={`${totalProducts} shown, ${rows.length} pending`}>
            <strong>{totalProducts}</strong><span>shown</span><i />
            <strong>{rows.length}</strong><span>pending</span>
          </div>
        </div>
      </section>

      <div className="qc-workspace">
        <section className="lo-card qc-queue-card">
          <div className="qc-card-heading">
            <div><span className="lo-eyebrow">Review queue</span><h2>Quantity check</h2></div>
            <div className="qc-keyboard-help"><kbd>Enter</kbd> Accept <kbd>Esc</kbd> No need <kbd>↑↓</kbd> Navigate</div>
          </div>
          {filteredRows.length ? (
            <div className="lo-scroll qc-grid-scroll">
            <table className="lo-table">
              <thead>
                <tr><th>#</th><th>Product Name</th><th className="lo-num">Or Qty</th><th className="lo-num">Stock</th><th className="lo-num">Pack</th><th>Desc</th><th className="lo-num">Sls Qty</th><th className="lo-num">MRP</th><th>LR Date</th><th>LS Date</th><th className="lo-num">Max Qty</th><th>Txn Date</th><th>Wanted</th></tr>
              </thead>
              <tbody>
                {filteredRows.map((row, index) => {
                  const value = edits[row.productcode] ?? row.orderqty
                  const isSelected = index === effectiveSelectedIndex
                  return (
                    <tr
                      key={row.productcode}
                      className={isSelected ? 'is-row-selected' : undefined}
                      onClick={() => focusRow(index)}
                    >
                      <td>{index + 1}</td>
                      <td><span className="qc-product-name" title={row.productname}>{row.productname}</span></td>
                      <td className="lo-num">
                        <div className="qc-qty-editor">
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
                          />
                          <button type="button" title="Accept quantity" aria-label={`Accept ${row.productname} quantity`} disabled={saving === row.productcode} onClick={(e) => { e.stopPropagation(); commit(row, value) }}><i className="bi bi-check-lg" /></button>
                          <button type="button" title="No need" aria-label={`Mark ${row.productname} as no need`} disabled={saving === row.productcode} onClick={(e) => { e.stopPropagation(); commit(row, 0) }}><i className="bi bi-x-lg" /></button>
                        </div>
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
              </tbody>
            </table>
            </div>
          ) : (
            <div className={`qc-empty-state${rows.length ? ' is-filtered' : ' is-complete'}`}>
              <span className="qc-empty-icon"><i className={`bi ${loading ? 'bi-arrow-repeat' : rows.length ? 'bi-funnel' : 'bi-check2-circle'}`} /></span>
              <h3>{loading ? 'Loading review queue…' : rows.length ? 'No products match these filters' : 'Quantity review is complete'}</h3>
              <p>{loading ? 'Fetching the latest order lines.' : rows.length ? 'Clear the filters or try another product name or code.' : `Every pending product for ${store || 'this store'} has been reviewed.`}</p>
              {!loading && (hasFilters
                ? <button type="button" className="lo-btn" onClick={resetFilters}><i className="bi bi-arrow-counterclockwise" /> Reset filters</button>
                : <Link to="/legacy-order/workspace" className="lo-btn lo-btn-primary">Continue to supplier assignment <i className="bi bi-arrow-right" /></Link>)}
            </div>
          )}
        </section>

        <section className="lo-card lo-activity qc-detail-card">
          <div className="qc-card-heading">
            <div><span className="lo-eyebrow">Selected product</span><h2>Product intelligence</h2></div>
            {selectedRow && <span className="qc-product-code">#{selectedRow.productcode}</span>}
          </div>
          {selectedRow ? (
            <ProductDetailPanel
              store={store}
              productCode={selectedRow.productcode}
              productName={selectedRow.productname}
              mode={mode}
              onError={setError}
            />
          ) : (
            <div className="qc-detail-empty">
              <span><i className="bi bi-box-seam" /></span>
              <strong>No product selected</strong>
              <p>Choose a product from the review queue to inspect purchase, sales, and monthly stock history.</p>
            </div>
          )}
        </section>
      </div>

      {selectedRow && (
      <section className="lo-card qc-history">
        <div className="qc-card-heading">
          <div><span className="lo-eyebrow">Previous decisions</span><h2>Order history</h2></div>
          <span className="qc-history-count">Last {Math.min(orderHistory.length, 25)} entries</span>
        </div>
        <div className="lo-scroll qc-history-scroll">
          <table className="lo-table">
            <thead><tr><th>Product Name</th><th className="lo-num">Or Qty</th><th className="lo-num">Org Order</th><th className="lo-num">Pack</th><th className="lo-num">MRP</th><th>Remarks</th><th>Wanted Date</th><th>Wanted</th><th>Or Supplier</th></tr></thead>
            <tbody>
              {orderHistory.map((row, i) => (
                <tr key={i}><td><span className="qc-product-name" title={row.ProductName}>{row.ProductName}</span></td><td className="lo-num">{row.Orqty ?? '—'}</td><td className="lo-num">{row.OrgOrderQty ?? '—'}</td><td className="lo-num">{row.saleunit ?? '—'}</td><td className="lo-num">{row.MRP ?? '—'}</td><td>{row.remarks ?? '—'}</td><td>{fmtDate(row.Wanteddate)}</td><td>{row.WantedType ?? '—'}</td><td>{row.Orsupplier ?? '—'}</td></tr>
              ))}
              {!orderHistory.length && <tr><td colSpan={9} className="lo-empty">No previous-order history for this product.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
      )}
    </div>
  )
}
