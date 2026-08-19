import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { legacyOrderService } from '../../services/legacyOrderService'
import type {
  AssignedOrderRow,
  LegacyStore,
  OrderMode,
  SupplierListItem,
  SupplierOrderMode,
  WorkspaceOrderRow,
} from '../../types/legacyOrder'
import './legacy-order.css'
import { FilterBar, FilterSearch, FilterSelect, FilterTabs } from '../../design-system/components/FilterBar'
import { ProductDetailPanel } from './ProductDetailPanel'

type View = 'review' | 'supplier' | 'assigned'

const num = (value: unknown): number => {
  const n = Number(value)
  return Number.isFinite(n) ? n : 0
}
const money = (value: number): string => value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })

export default function OrderWorkspacePage() {
  const [stores, setStores] = useState<LegacyStore[]>([])
  const [store, setStore] = useState('')
  const [detailMode, setDetailMode] = useState<OrderMode>('local')
  const [view, setView] = useState<View>('review')
  const [supplierMode, setSupplierMode] = useState<SupplierOrderMode>('history')

  // Supplier search panel (dgvSupplierList).
  const [supplierSearch, setSupplierSearch] = useState('')
  const [suppliers, setSuppliers] = useState<SupplierListItem[]>([])
  const [supplier, setSupplier] = useState<SupplierListItem | null>(null)

  // Grid rows for review/supplier views, and the assigned view.
  const [rows, setRows] = useState<WorkspaceOrderRow[]>([])
  const [assigned, setAssigned] = useState<AssignedOrderRow[]>([])
  const [edits, setEdits] = useState<Record<number, number>>({})
  // Session status overrides so a row turns green/normal on assign toggle
  // without a full reload (orders_by_supplier only returns status=0 rows).
  const [statusOverride, setStatusOverride] = useState<Record<number, number>>({})
  const [savingQty, setSavingQty] = useState<number | null>(null)
  const [assigningCode, setAssigningCode] = useState<number | null>(null)
  const [selectedCode, setSelectedCode] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [banner, setBanner] = useState<string | null>(null)

  const gridRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    legacyOrderService.listStores()
      .then((list) => {
        setStores(list)
        if (list.length) setStore(list[0].store_name)
      })
      .catch((e: Error) => setError(e.message))
  }, [])

  // Reset selection/edits whenever the store or view context changes.
  const resetGrid = useCallback(() => {
    setEdits({})
    setStatusOverride({})
    setSelectedCode(null)
  }, [])

  // Debounced supplier search (VB txtSupplierSearch_TextChanged).
  useEffect(() => {
    if (view !== 'supplier' && view !== 'assigned') return
    if (!store) return
    const handle = window.setTimeout(() => {
      legacyOrderService.suppliers(store, supplierSearch)
        .then(setSuppliers)
        .catch((e: Error) => setError(e.message))
    }, 250)
    return () => window.clearTimeout(handle)
  }, [store, supplierSearch, view])

  // Load the grid for the active context.
  const loadGrid = useCallback(() => {
    if (!store) return
    resetGrid()
    setLoading(true)
    const done = () => setLoading(false)
    if (view === 'review') {
      legacyOrderService.orders(store)
        .then((data) => setRows(data))
        .catch((e: Error) => setError(e.message))
        .finally(done)
    } else if (view === 'supplier') {
      if (!supplier) { setRows([]); done(); return }
      legacyOrderService.ordersBySupplier(store, supplier.supplier_code, supplierMode)
        .then(setRows)
        .catch((e: Error) => setError(e.message))
        .finally(done)
    } else {
      if (!supplier) { setAssigned([]); done(); return }
      legacyOrderService.assignedOrders(store, supplier.supplier_code)
        .then(setAssigned)
        .catch((e: Error) => setError(e.message))
        .finally(done)
    }
  }, [store, view, supplier, supplierMode, resetGrid])

  useEffect(() => { loadGrid() }, [loadGrid])

  // Switching store clears supplier context; switching away from review keeps it.
  useEffect(() => { setSupplier(null); setSuppliers([]); setSupplierSearch('') }, [store])

  const statusOf = (row: WorkspaceOrderRow) => statusOverride[row.ProductCode] ?? row.Status
  const qtyOf = (row: WorkspaceOrderRow) => edits[row.ProductCode] ?? row.OrderQty

  const saveQty = useCallback((row: WorkspaceOrderRow, value: number) => {
    if (!store) return
    setSavingQty(row.ProductCode)
    legacyOrderService.updateOrderQty(store, row.ProductCode, value)
      .then(() => setRows((cur) => cur.map((r) => (r.ProductCode === row.ProductCode ? { ...r, OrderQty: value } : r))))
      .catch((e: Error) => setError(e.message))
      .finally(() => setSavingQty(null))
  }, [store])

  const toggleAssign = useCallback((row: WorkspaceOrderRow) => {
    if (!store || !supplier) return
    setAssigningCode(row.ProductCode)
    setBanner(null)
    legacyOrderService.assignSupplier(store, row.ProductCode, supplier.supplier_code, supplier.supplier_name)
      .then((result) => {
        setStatusOverride((cur) => ({ ...cur, [row.ProductCode]: result.status }))
        setBanner(
          result.status === 1
            ? `Assigned ${row.ProductName} → ${supplier.supplier_name} (qty ${result.order_qty}).`
            : `Cleared supplier from ${row.ProductName}.`,
        )
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setAssigningCode(null))
  }, [store, supplier])

  const isStock = view === 'supplier' && supplierMode === 'stock'
  const canAssign = view === 'supplier' && Boolean(supplier)

  const footer = useMemo(() => {
    let qty = 0
    let value = 0
    for (const row of rows) {
      const q = num(qtyOf(row))
      qty += q
      value += q * num(row.PurchasePrice)
    }
    return { count: rows.length, qty, value }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, edits])

  const selectedRow = useMemo(() => {
    if (selectedCode == null) return null
    if (view === 'assigned') return assigned.find((r) => r.ProductCode === selectedCode) ?? null
    return rows.find((r) => r.ProductCode === selectedCode) ?? null
  }, [selectedCode, rows, assigned, view])

  const onGridKey = (e: React.KeyboardEvent) => {
    const list: { ProductCode: number }[] = view === 'assigned' ? assigned : rows
    if (!list.length) return
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return
    e.preventDefault()
    const idx = list.findIndex((r) => r.ProductCode === selectedCode)
    const next = e.key === 'ArrowDown' ? Math.min(list.length - 1, idx + 1) : Math.max(0, idx - 1)
    setSelectedCode(list[next < 0 ? 0 : next].ProductCode)
  }

  return (
    <div className="legacy-order">
      <header className="lo-header">
        <div>
          <h1>Order Management · Workspace</h1>
          <p className="lo-sub">Pick a supplier, review its orderable products by purchase history or live stock, edit quantities, and assign the supplier per line — the VB.NET dgvMain ordering screen.</p>
        </div>
        <div className="lo-actions">
          <Link to="/legacy-order/qty-check" className="lo-btn"><i className="bi bi-table" /> Qty Check Grid</Link>
          <Link to="/legacy-order" className="lo-btn"><i className="bi bi-arrow-left" /> Back to Console</Link>
        </div>
      </header>

      {error && <div className="lo-error" role="alert">{error}<button type="button" onClick={() => setError(null)} aria-label="Dismiss">×</button></div>}
      {banner && <div className="lo-success"><i className="bi bi-check-circle" /> {banner}<button type="button" onClick={() => setBanner(null)} aria-label="Dismiss" style={{ marginLeft: 'auto', background: 'none', border: 0, cursor: 'pointer' }}>×</button></div>}

      <section className="lo-card">
        <div className="lo-section-title">
          <FilterBar compact className="lo-row" ariaLabel="Order workspace filters">
            <FilterSelect label="Store" ariaLabel="Store" value={store} onChange={setStore}>
              {stores.map((s) => <option key={s.store_name} value={s.store_name}>{s.store_name}</option>)}
            </FilterSelect>
            <FilterTabs
              value={view}
              ariaLabel="Workspace view"
              options={[
                { value: 'review', label: 'Review All' },
                { value: 'supplier', label: 'By Supplier' },
                { value: 'assigned', label: 'Assigned' },
              ]}
              onChange={(v) => setView(v as View)}
            />
            {view === 'supplier' && (
              <FilterTabs
                value={supplierMode}
                ariaLabel="Supplier filter mode"
                options={[{ value: 'history', label: 'History' }, { value: 'stock', label: 'Live Stock' }]}
                onChange={(v) => setSupplierMode(v as SupplierOrderMode)}
              />
            )}
            <FilterTabs
              value={detailMode}
              ariaLabel="Detail source"
              options={[{ value: 'local', label: 'Local DB' }, { value: 'remote', label: 'Remote DB' }]}
              onChange={(v) => setDetailMode(v as OrderMode)}
            />
          </FilterBar>
          <span className="lo-count">{view === 'assigned' ? assigned.length : rows.length} products</span>
        </div>
      </section>

      <div className="lo-lower-grid">
        <section className="lo-card">
          {(view === 'supplier' || view === 'assigned') && (
            <div className="lo-supplier-pick">
              <FilterBar compact ariaLabel="Supplier search">
                <FilterSearch value={supplierSearch} placeholder="Search supplier…" ariaLabel="Search suppliers" onChange={setSupplierSearch} />
              </FilterBar>
              <div className="lo-supplier-grid lo-supplier-picklist" role="listbox" aria-label="Suppliers">
                {suppliers.map((s) => (
                  <button
                    type="button"
                    role="option"
                    aria-selected={supplier?.supplier_code === s.supplier_code}
                    className={`lo-supplier-row${supplier?.supplier_code === s.supplier_code ? ' is-selected' : ''}`}
                    key={s.supplier_code}
                    onClick={() => setSupplier(s)}
                  >
                    <span><strong>{s.supplier_name}</strong><small>{s.supplier_code}</small></span>
                    <span className="lo-review-link"><i className="bi bi-chevron-right" /></span>
                  </button>
                ))}
                {!suppliers.length && <div className="lo-empty">{supplierSearch ? 'No matching suppliers.' : 'Type to search suppliers.'}</div>}
              </div>
            </div>
          )}

          <h2>{view === 'assigned' ? 'Assigned order' : view === 'supplier' ? (supplier ? `${supplier.supplier_name} · orderable` : 'Select a supplier') : 'Order grid'}</h2>

          {view === 'assigned' ? (
            <div className="lo-scroll" tabIndex={0} onKeyDown={onGridKey}>
              <table className="lo-table">
                <thead><tr><th>#</th><th>Product Name</th><th className="lo-num">Or Qty</th><th className="lo-num">Stock</th><th className="lo-num">MRP</th><th>Supplier</th><th>Remarks</th></tr></thead>
                <tbody>
                  {assigned.map((row, i) => (
                    <tr key={row.ProductCode} className={selectedCode === row.ProductCode ? 'lo-supplier-row is-selected' : undefined} onClick={() => setSelectedCode(row.ProductCode)}>
                      <td>{i + 1}</td>
                      <td><span className="qc-product-name" title={row.ProductName}>{row.ProductName}</span></td>
                      <td className="lo-num">{row.OrderQty}</td>
                      <td className="lo-num">{row.TotalStock}</td>
                      <td className="lo-num">{num(row.MRP).toFixed(2)}</td>
                      <td>{row.OrSupplier ?? '—'}</td>
                      <td>{row.Remarks ?? '—'}</td>
                    </tr>
                  ))}
                  {!assigned.length && <tr><td colSpan={7} className="lo-empty">{loading ? 'Loading…' : supplier ? 'No products assigned to this supplier yet.' : 'Select a supplier to see its assigned order.'}</td></tr>}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="lo-scroll" ref={gridRef} tabIndex={0} onKeyDown={onGridKey}>
              <table className="lo-table">
                <thead>
                  <tr>
                    <th>#</th><th>Product Name</th><th className="lo-num">Or Qty</th><th className="lo-num">Stock</th>
                    {isStock && <><th className="lo-num">S.Stock</th><th className="lo-num">Disc</th><th className="lo-num">MinQty</th><th>Rack</th></>}
                    <th className="lo-num">Pack</th><th>Desc</th><th className="lo-num">Sls</th><th className="lo-num">MRP</th><th>Wanted</th>
                    {canAssign && <th>Action</th>}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, i) => {
                    const assignedRow = statusOf(row) === 1
                    const value = qtyOf(row)
                    const colCount = 9 + (isStock ? 4 : 0) + (canAssign ? 1 : 0)
                    return (
                      <tr
                        key={row.ProductCode}
                        className={`${selectedCode === row.ProductCode ? 'lo-supplier-row is-selected' : ''}${assignedRow ? ' lo-row-assigned' : ''}`}
                        onClick={() => setSelectedCode(row.ProductCode)}
                        data-col-count={colCount}
                      >
                        <td>{i + 1}</td>
                        <td><span className="qc-product-name" title={row.ProductName}>{row.ProductName}</span></td>
                        <td className="lo-num">
                          <input
                            type="number"
                            min={0}
                            aria-label={`${row.ProductName} order quantity`}
                            value={value}
                            disabled={savingQty === row.ProductCode || assignedRow}
                            onClick={(e) => e.stopPropagation()}
                            onFocus={() => setSelectedCode(row.ProductCode)}
                            onChange={(e) => setEdits((cur) => ({ ...cur, [row.ProductCode]: Number(e.target.value) }))}
                            onBlur={(e) => { const v = Number(e.target.value); if (v !== row.OrderQty) saveQty(row, v) }}
                            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); saveQty(row, value) } }}
                            style={{ width: '4rem' }}
                          />
                        </td>
                        <td className="lo-num">{row.TotalStock}</td>
                        {isStock && <>
                          <td className="lo-num">{row.S_Stock ?? '—'}</td>
                          <td className="lo-num">{row.Discount ?? '—'}</td>
                          <td className="lo-num">{row.MinQty ?? '—'}</td>
                          <td>{row.Rack || '—'}</td>
                        </>}
                        <td className="lo-num">{row.SaleUnit}</td>
                        <td>{row.UnitDescription}</td>
                        <td className="lo-num">{row.SLSQty}</td>
                        <td className="lo-num">{num(row.MRP).toFixed(2)}</td>
                        <td>{row.WantedType ?? '—'}</td>
                        {canAssign && (
                          <td>
                            <button
                              type="button"
                              className={`lo-btn ${assignedRow ? 'lo-btn-danger' : 'lo-btn-primary'}`}
                              disabled={assigningCode === row.ProductCode}
                              onClick={(e) => { e.stopPropagation(); toggleAssign(row) }}
                            >
                              {assigningCode === row.ProductCode ? '…' : assignedRow ? 'Unassign' : 'Assign'}
                            </button>
                          </td>
                        )}
                      </tr>
                    )
                  })}
                  {!rows.length && <tr><td colSpan={9 + (isStock ? 4 : 0) + (canAssign ? 1 : 0)} className="lo-empty">{loading ? 'Loading…' : view === 'supplier' ? (supplier ? 'No orderable products for this supplier.' : 'Search and select a supplier.') : 'No open order rows for this store.'}</td></tr>}
                </tbody>
              </table>
            </div>
          )}

          {view !== 'assigned' && (
            <div className="lo-footer-totals">
              <span>{footer.count} products</span>
              <span>Σ Qty <strong>{footer.qty}</strong></span>
              <span>Σ Value <strong>{money(footer.value)}</strong></span>
            </div>
          )}
        </section>

        <section className="lo-card lo-activity">
          <h2>Product detail</h2>
          <ProductDetailPanel
            store={store}
            productCode={selectedCode}
            productName={selectedRow ? selectedRow.ProductName : undefined}
            mode={detailMode}
            onError={setError}
          />
        </section>
      </div>
    </div>
  )
}
