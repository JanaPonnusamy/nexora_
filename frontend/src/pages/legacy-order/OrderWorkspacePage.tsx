import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { legacyOrderService } from '../../services/legacyOrderService'
import type {
  AssignedOrderRow,
  LegacyStore,
  OrderHistoryRow,
  OrderMode,
  OrderWorkflowSummary,
  QtyCheckRow,
  SupplierListItem,
  SupplierOrderMode,
  WorkspaceOrderRow,
} from '../../types/legacyOrder'
import './legacy-order.css'
import { FilterBar, FilterSearch, FilterSelect, FilterTabs } from '../../design-system/components/FilterBar'
import { ProductDetailPanel } from './ProductDetailPanel'
import { fmtDate } from './format'

// The single VB.NET-style ordering screen: quantity review AND supplier
// assignment on one page. "Qty Review" walks pending lines one at a time
// (Enter accepts, Esc = no need); the supplier views pick a supplier and
// assign lines. The shared right-hand panel shows product intelligence and the
// slim strip below shows previous-order history for the selected product.
type View = 'qty' | 'review' | 'supplier' | 'assigned'

const num = (value: unknown): number => {
  const n = Number(value)
  return Number.isFinite(n) ? n : 0
}
const money = (value: number): string => value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })

export default function OrderWorkspacePage() {
  const [stores, setStores] = useState<LegacyStore[]>([])
  const [store, setStore] = useState('')
  const [detailMode, setDetailMode] = useState<OrderMode>('local')
  const [view, setView] = useState<View>('qty')
  const [supplierMode, setSupplierMode] = useState<SupplierOrderMode>('history')

  // Supplier picker (dgvSupplierList → VB-style combo dropdown).
  const [suppliers, setSuppliers] = useState<SupplierListItem[]>([])
  const [supplier, setSupplier] = useState<SupplierListItem | null>(null)

  // Grid rows per view. Qty Review uses its own pending-lines source; the
  // Review/By-Supplier views share the workspace order rows; Assigned is
  // separate.
  const [qtyRows, setQtyRows] = useState<QtyCheckRow[]>([])
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

  // Filters (from the old Qty-Check screen), applied to whichever grid is live.
  const [search, setSearch] = useState('')
  const [productType, setProductType] = useState('All')
  const [wantedType, setWantedType] = useState('All')

  // Workflow summary drives the compact Finalize control + the FINALIZED lock;
  // the bulky step-header panel is gone by design.
  const [workflow, setWorkflow] = useState<OrderWorkflowSummary | null>(null)
  const [workflowBusy, setWorkflowBusy] = useState(false)

  const [orderHistory, setOrderHistory] = useState<OrderHistoryRow[]>([])
  // Previous-decisions strip is a compact, collapsible footer so the product
  // grid + intelligence keep the vertical priority.
  const [historyOpen, setHistoryOpen] = useState(true)

  const gridRef = useRef<HTMLDivElement | null>(null)
  const qtyInputRefs = useRef<Array<HTMLInputElement | null>>([])

  useEffect(() => {
    legacyOrderService.listStores()
      .then((list) => {
        setStores(list)
        if (list.length) setStore(list[0].store_name)
      })
      .catch((e: Error) => setError(e.message))
  }, [])

  const loadWorkflow = useCallback(() => {
    if (!store) return
    legacyOrderService.orderWorkflow(store)
      .then(setWorkflow)
      .catch((e: Error) => setError(e.message))
  }, [store])

  useEffect(() => { loadWorkflow() }, [loadWorkflow])

  // Reset selection/edits whenever the store or view context changes.
  const resetGrid = useCallback(() => {
    setEdits({})
    setStatusOverride({})
    setSelectedCode(null)
  }, [])

  // Load the full supplier list for the store combo (empty search = all).
  useEffect(() => {
    if (view !== 'supplier' && view !== 'assigned') return
    if (!store) return
    legacyOrderService.suppliers(store, '')
      .then(setSuppliers)
      .catch((e: Error) => setError(e.message))
  }, [store, view])

  // Load the grid for the active context.
  const loadGrid = useCallback(() => {
    if (!store) return
    resetGrid()
    setLoading(true)
    const done = () => setLoading(false)
    if (view === 'qty') {
      legacyOrderService.qtyCheckRows(store)
        .then(setQtyRows)
        .catch((e: Error) => setError(e.message))
        .finally(done)
    } else if (view === 'review') {
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

  useEffect(() => {
    const handle = window.setTimeout(loadGrid, 0)
    return () => window.clearTimeout(handle)
  }, [loadGrid])

  // Switching store clears supplier context and reloads the grid.
  const changeStore = (nextStore: string) => {
    setSupplier(null)
    setSuppliers([])
    setStore(nextStore)
  }

  const finalized = workflow?.status === 'FINALIZED'

  const statusOf = (row: WorkspaceOrderRow) => statusOverride[row.ProductCode] ?? row.Status
  const qtyOf = (row: WorkspaceOrderRow) => edits[row.ProductCode] ?? row.OrderQty

  const term = search.trim().toLowerCase()
  const matchText = useCallback((name: string, code: number) =>
    !term || name.toLowerCase().includes(term) || String(code).includes(term), [term])

  const wantedTypes = useMemo(() => {
    const set = new Set<string>()
    qtyRows.forEach((r) => { if (r.wantedtype) set.add(r.wantedtype) })
    rows.forEach((r) => { if (r.WantedType) set.add(r.WantedType) })
    assigned.forEach((r) => { if (r.WantedType) set.add(r.WantedType) })
    return Array.from(set).sort()
  }, [qtyRows, rows, assigned])

  const filteredQty = useMemo(() => qtyRows.filter((r) => (
    matchText(r.productname, r.productcode)
    && (productType === 'All' || r.producttypename === productType)
    && (wantedType === 'All' || r.wantedtype === wantedType)
  )), [qtyRows, matchText, productType, wantedType])

  const filteredRows = useMemo(() => rows.filter((r) => (
    matchText(r.ProductName, r.ProductCode)
    && (productType === 'All' || r.ProductTypeName === productType)
    && (wantedType === 'All' || r.WantedType === wantedType)
  )), [rows, matchText, productType, wantedType])

  const filteredAssigned = useMemo(() => assigned.filter((r) => (
    matchText(r.ProductName, r.ProductCode)
    && (wantedType === 'All' || r.WantedType === wantedType)
  )), [assigned, matchText, wantedType])

  // ----- Qty Review commit (accept / no-need), removes the pending line -----
  const commitQty = useCallback((productCode: number, value: number, nextCode: number | null, focusIndex: number) => {
    if (!store) return
    setSavingQty(productCode)
    legacyOrderService.updateQtyCheck(store, productCode, value)
      .then(() => {
        setQtyRows((cur) => cur.filter((r) => r.productcode !== productCode))
        setEdits((cur) => { const n = { ...cur }; delete n[productCode]; return n })
        setSelectedCode(nextCode)
        requestAnimationFrame(() => qtyInputRefs.current[focusIndex]?.focus())
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => { setSavingQty(null); loadWorkflow() })
  }, [store, loadWorkflow])

  const focusQty = (index: number) => {
    const clamped = Math.max(0, Math.min(filteredQty.length - 1, index))
    const row = filteredQty[clamped]
    if (row) setSelectedCode(row.productcode)
    requestAnimationFrame(() => qtyInputRefs.current[clamped]?.focus())
  }

  const onQtyKeyDown = (e: React.KeyboardEvent<HTMLInputElement>, index: number) => {
    const row = filteredQty[index]
    if (!row) return
    if (e.key === 'Enter' || e.key === 'Escape') {
      e.preventDefault()
      const value = e.key === 'Enter' ? (edits[row.productcode] ?? row.orderqty) : 0
      // After removal the list shifts up, so the same index lands on the next row.
      const next = filteredQty[index + 1] ?? filteredQty[index - 1] ?? null
      commitQty(row.productcode, value, next ? next.productcode : null, index)
    } else if (e.key === 'ArrowDown') {
      e.preventDefault(); focusQty(index + 1)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault(); focusQty(index - 1)
    }
  }

  // ----- Workspace qty save (in place) + supplier assign -----
  const saveQty = useCallback((row: WorkspaceOrderRow, value: number) => {
    if (!store) return
    setSavingQty(row.ProductCode)
    legacyOrderService.updateOrderQty(store, row.ProductCode, value)
      .then(() => setRows((cur) => cur.map((r) => (r.ProductCode === row.ProductCode ? { ...r, OrderQty: value } : r))))
      .catch((e: Error) => setError(e.message))
      .finally(() => { setSavingQty(null); loadWorkflow() })
  }, [store, loadWorkflow])

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
      .finally(() => { setAssigningCode(null); loadWorkflow() })
  }, [store, supplier, loadWorkflow])

  const finalize = (reopen: boolean) => {
    if (!store) return
    const note = reopen
      ? window.prompt('Why is this order being reopened?')
      : window.prompt('Optional finalization note:')
    if (note === null) return
    setWorkflowBusy(true)
    const call = reopen
      ? legacyOrderService.reopenOrder(store, note)
      : legacyOrderService.finalizeOrder(store, note)
    call.then(setWorkflow)
      .catch((e: Error) => setError(e.message))
      .finally(() => setWorkflowBusy(false))
  }

  const isStock = view === 'supplier' && supplierMode === 'stock'
  const canAssign = view === 'supplier' && Boolean(supplier)

  const footer = useMemo(() => {
    let qty = 0
    let value = 0
    for (const row of filteredRows) {
      const q = num(qtyOf(row))
      qty += q
      value += q * num(row.PurchasePrice)
    }
    return { count: filteredRows.length, qty, value }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filteredRows, edits])

  const activeCount = view === 'qty' ? filteredQty.length
    : view === 'assigned' ? filteredAssigned.length
      : filteredRows.length

  // Product name for the detail panel + which list the selection belongs to.
  const selectedName = useMemo(() => {
    if (selectedCode == null) return undefined
    return qtyRows.find((r) => r.productcode === selectedCode)?.productname
      ?? rows.find((r) => r.ProductCode === selectedCode)?.ProductName
      ?? assigned.find((r) => r.ProductCode === selectedCode)?.ProductName
  }, [selectedCode, qtyRows, rows, assigned])

  // Previous-order history for the selected product (bottom strip).
  useEffect(() => {
    if (!store || selectedCode == null) { setOrderHistory([]); return }
    legacyOrderService.qtyCheckOrderHistory(store, selectedCode)
      .then(setOrderHistory)
      .catch((e: Error) => setError(e.message))
  }, [store, selectedCode])

  const onGridKey = (e: React.KeyboardEvent) => {
    const list: { ProductCode: number }[] = view === 'assigned' ? filteredAssigned : filteredRows
    if (!list.length) return
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return
    e.preventDefault()
    const idx = list.findIndex((r) => r.ProductCode === selectedCode)
    const next = e.key === 'ArrowDown' ? Math.min(list.length - 1, idx + 1) : Math.max(0, idx - 1)
    setSelectedCode(list[next < 0 ? 0 : next].ProductCode)
  }

  const gridTitle = view === 'qty' ? 'Quantity check'
    : view === 'assigned' ? 'Assigned order'
      : view === 'supplier' ? (supplier ? `${supplier.supplier_name} · orderable` : 'Select a supplier')
        : 'Order grid'

  return (
    <div className="legacy-order lo-merged">
      <header className="lo-merged-head">
        <div className="lo-merged-title">
          <h1 className="lo-merged-app">Order Management</h1>
          {store ? <span className="lo-merged-store">{store}</span> : <span className="lo-merged-store lo-dim">Select a store</span>}
          {workflow?.order_id != null && <span className="lo-merged-order">#{workflow.order_id}</span>}
          {workflow && <span className={`lo-chip lo-chip-${finalized || workflow.ready ? 'success' : 'running'}`}>{workflow.status.replace(/_/g, ' ')}</span>}
          {workflow && (
            <span className="lo-merged-metrics">
              <strong>{workflow.qty_pending}</strong> pending · <strong>{workflow.assigned_lines}</strong> assigned · <strong>{workflow.unassigned_lines}</strong> open
            </span>
          )}
        </div>
        <div className="lo-actions">
          {finalized ? (
            <button type="button" className="lo-btn lo-btn-sm" disabled={workflowBusy} onClick={() => finalize(true)}><i className="bi bi-unlock" /> Reopen</button>
          ) : (
            <button type="button" className="lo-btn lo-btn-sm lo-btn-primary" disabled={workflowBusy || !workflow?.ready} title={workflow?.ready ? 'Lock this order for downstream processing' : 'Complete quantity review and supplier assignment first'} onClick={() => finalize(false)}><i className="bi bi-lock" /> Finalize</button>
          )}
          <Link to="/legacy-order" className="lo-btn lo-btn-sm"><i className="bi bi-arrow-left" /> Console</Link>
        </div>
      </header>

      {error && <div className="lo-error" role="alert">{error}<button type="button" onClick={() => setError(null)} aria-label="Dismiss">×</button></div>}
      {banner && <div className="lo-success"><i className="bi bi-check-circle" /> {banner}<button type="button" onClick={() => setBanner(null)} aria-label="Dismiss" style={{ marginLeft: 'auto', background: 'none', border: 0, cursor: 'pointer' }}>×</button></div>}

      <section className="lo-card lo-merged-filter">
        <div className="lo-section-title">
          <FilterBar compact className="lo-row" ariaLabel="Order workspace filters">
            <FilterSelect label="Store" ariaLabel="Store" value={store} onChange={changeStore}>
              {stores.map((s) => <option key={s.store_name} value={s.store_name}>{s.store_name}</option>)}
            </FilterSelect>
            <FilterTabs
              value={view}
              ariaLabel="Workspace view"
              options={[
                { value: 'qty', label: 'Qty Review' },
                { value: 'review', label: 'Review All' },
                { value: 'supplier', label: 'By Supplier' },
                { value: 'assigned', label: 'Assigned' },
              ]}
              onChange={(v) => setView(v as View)}
            />
            {(view === 'supplier' || view === 'assigned') && (
              <FilterSelect
                label="Supplier"
                ariaLabel="Supplier"
                value={supplier?.supplier_code ?? ''}
                onChange={(code) => setSupplier(suppliers.find((s) => s.supplier_code === code) ?? null)}
              >
                <option value="">Select supplier…</option>
                {suppliers.map((s) => <option key={s.supplier_code} value={s.supplier_code}>{s.supplier_name}</option>)}
              </FilterSelect>
            )}
            {view === 'supplier' && (
              <FilterTabs
                value={supplierMode}
                ariaLabel="Supplier filter mode"
                options={[{ value: 'history', label: 'History' }, { value: 'stock', label: 'Live Stock' }]}
                onChange={(v) => setSupplierMode(v as SupplierOrderMode)}
              />
            )}
            <FilterSearch className="qc-product-search" value={search} placeholder="Search product or code…" ariaLabel="Search products" onChange={setSearch} />
            <FilterSelect label="Product type" ariaLabel="Product type" value={productType} onChange={setProductType}>
              <option value="All">All products</option>
              <option value="Pharma">Pharma</option>
              <option value="Non Pharma">Non Pharma</option>
            </FilterSelect>
            <FilterSelect label="Wanted reason" ariaLabel="Wanted reason" value={wantedType} onChange={setWantedType}>
              <option value="All">All reasons</option>
              {wantedTypes.map((value) => <option key={value} value={value}>{value}</option>)}
            </FilterSelect>
            <FilterTabs
              value={detailMode}
              ariaLabel="Detail source"
              options={[{ value: 'local', label: 'Local DB' }, { value: 'remote', label: 'Remote DB' }]}
              onChange={(v) => setDetailMode(v as OrderMode)}
            />
          </FilterBar>
          <span className="lo-count">{activeCount} products</span>
        </div>
      </section>

      <div className="qc-workspace">
        <section className="lo-card qc-queue-card">
          <div className="qc-card-heading">
            <div><span className="lo-eyebrow">{view === 'qty' ? 'Review queue' : 'Order grid'}</span><h2>{gridTitle}</h2></div>
            {view === 'qty'
              ? <div className="qc-keyboard-help"><kbd>Enter</kbd> Accept <kbd>Esc</kbd> No need <kbd>↑↓</kbd> Navigate</div>
              : <span className="lo-count">{activeCount} products</span>}
          </div>

          {view === 'qty' ? (
            <div className="lo-scroll qc-grid-scroll">
              <table className="lo-table lo-dense">
                <thead>
                  <tr><th>#</th><th>Product Name</th><th className="lo-num">Or Qty</th><th className="lo-num">Stock</th><th className="lo-num">Pack</th><th>Desc</th><th className="lo-num">Sls Qty</th><th className="lo-num">MRP</th><th>LR Date</th><th>LS Date</th><th className="lo-num">Max Qty</th><th>Txn Date</th><th>Wanted</th></tr>
                </thead>
                <tbody>
                  {filteredQty.map((row, index) => {
                    const value = edits[row.productcode] ?? row.orderqty
                    return (
                      <tr key={row.productcode} className={selectedCode === row.productcode ? 'is-row-selected' : undefined} onClick={() => setSelectedCode(row.productcode)}>
                        <td>{index + 1}</td>
                        <td><span className="qc-product-name" title={row.productname}>{row.productname}</span></td>
                        <td className="lo-num">
                          <input
                            ref={(el) => { qtyInputRefs.current[index] = el }}
                            className="qc-qty-input"
                            type="number"
                            min={0}
                            aria-label={`${row.productname} order quantity`}
                            value={value}
                            disabled={savingQty === row.productcode || finalized}
                            onClick={(e) => e.stopPropagation()}
                            onFocus={() => setSelectedCode(row.productcode)}
                            onChange={(e) => setEdits((cur) => ({ ...cur, [row.productcode]: Number(e.target.value) }))}
                            onKeyDown={(e) => onQtyKeyDown(e, index)}
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
                  {!filteredQty.length && <tr><td colSpan={13} className="lo-empty">{loading ? 'Loading…' : qtyRows.length ? 'No products match these filters.' : `Every pending product for ${store || 'this store'} has been reviewed.`}</td></tr>}
                </tbody>
              </table>
            </div>
          ) : view === 'assigned' ? (
            <div className="lo-scroll qc-grid-scroll" tabIndex={0} onKeyDown={onGridKey}>
              <table className="lo-table lo-dense">
                <thead><tr><th>#</th><th>Product Name</th><th className="lo-num">Or Qty</th><th className="lo-num">Stock</th><th className="lo-num">MRP</th><th>Supplier</th><th>Remarks</th></tr></thead>
                <tbody>
                  {filteredAssigned.map((row, i) => (
                    <tr key={row.ProductCode} className={selectedCode === row.ProductCode ? 'is-row-selected' : undefined} onClick={() => setSelectedCode(row.ProductCode)}>
                      <td>{i + 1}</td>
                      <td><span className="qc-product-name" title={row.ProductName}>{row.ProductName}</span></td>
                      <td className="lo-num">{row.OrderQty}</td>
                      <td className="lo-num">{row.TotalStock}</td>
                      <td className="lo-num">{num(row.MRP).toFixed(2)}</td>
                      <td>{row.OrSupplier ?? '—'}</td>
                      <td>{row.Remarks ?? '—'}</td>
                    </tr>
                  ))}
                  {!filteredAssigned.length && <tr><td colSpan={7} className="lo-empty">{loading ? 'Loading…' : supplier ? 'No products assigned to this supplier yet.' : 'Select a supplier to see its assigned order.'}</td></tr>}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="lo-scroll qc-grid-scroll" ref={gridRef} tabIndex={0} onKeyDown={onGridKey}>
              <table className="lo-table lo-dense">
                <thead>
                  <tr>
                    <th>#</th><th>Product Name</th><th className="lo-num">Or Qty</th><th className="lo-num">Stock</th>
                    {isStock && <><th className="lo-num">S.Stock</th><th className="lo-num">Disc</th><th className="lo-num">MinQty</th><th>Rack</th></>}
                    <th className="lo-num">Pack</th><th>Desc</th><th className="lo-num">Sls</th><th className="lo-num">MRP</th><th>Wanted</th>
                    {canAssign && <th>Action</th>}
                  </tr>
                </thead>
                <tbody>
                  {filteredRows.map((row, i) => {
                    const assignedRow = statusOf(row) === 1
                    const value = qtyOf(row)
                    const colCount = 9 + (isStock ? 4 : 0) + (canAssign ? 1 : 0)
                    return (
                      <tr
                        key={row.ProductCode}
                        className={`${selectedCode === row.ProductCode ? 'is-row-selected' : ''}${assignedRow ? ' lo-row-assigned' : ''}`.trim() || undefined}
                        onClick={() => setSelectedCode(row.ProductCode)}
                        data-col-count={colCount}
                      >
                        <td>{i + 1}</td>
                        <td><span className="qc-product-name" title={row.ProductName}>{row.ProductName}</span></td>
                        <td className="lo-num">
                          <input
                            className="qc-qty-input"
                            type="number"
                            min={0}
                            aria-label={`${row.ProductName} order quantity`}
                            value={value}
                            disabled={savingQty === row.ProductCode || assignedRow || finalized}
                            onClick={(e) => e.stopPropagation()}
                            onFocus={() => setSelectedCode(row.ProductCode)}
                            onChange={(e) => setEdits((cur) => ({ ...cur, [row.ProductCode]: Number(e.target.value) }))}
                            onBlur={(e) => { const v = Number(e.target.value); if (v !== row.OrderQty) saveQty(row, v) }}
                            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); saveQty(row, value) } }}
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
                              disabled={assigningCode === row.ProductCode || finalized}
                              onClick={(e) => { e.stopPropagation(); toggleAssign(row) }}
                            >
                              {assigningCode === row.ProductCode ? '…' : assignedRow ? 'Unassign' : 'Assign'}
                            </button>
                          </td>
                        )}
                      </tr>
                    )
                  })}
                  {!filteredRows.length && <tr><td colSpan={9 + (isStock ? 4 : 0) + (canAssign ? 1 : 0)} className="lo-empty">{loading ? 'Loading…' : view === 'supplier' ? (supplier ? 'No orderable products for this supplier.' : 'Search and select a supplier.') : 'No open order rows for this store.'}</td></tr>}
                </tbody>
              </table>
            </div>
          )}

          {(view === 'review' || view === 'supplier') && (
            <div className="lo-footer-totals">
              <span>{footer.count} products</span>
              <span>Σ Qty <strong>{footer.qty}</strong></span>
              <span>Σ Value <strong>{money(footer.value)}</strong></span>
            </div>
          )}
        </section>

        <section className="lo-card lo-activity qc-detail-card">
          <div className="qc-card-heading qc-detail-heading">
            <span className="lo-eyebrow">Product intelligence</span>
            {selectedName && <span className="qc-pi-name" title={selectedName}>{selectedName}</span>}
            {selectedCode != null && <span className="qc-product-code">#{selectedCode}</span>}
          </div>
          <ProductDetailPanel
            store={store}
            productCode={selectedCode}
            mode={detailMode}
            onError={setError}
          />
        </section>
      </div>

      <section className={`lo-card qc-history lo-merged-history${historyOpen ? '' : ' is-collapsed'}`}>
        <div className="qc-card-heading">
          <button type="button" className="lo-history-toggle" aria-expanded={historyOpen} onClick={() => setHistoryOpen((v) => !v)}>
            <i className={`bi ${historyOpen ? 'bi-chevron-down' : 'bi-chevron-right'}`} />
            <span className="lo-eyebrow">Previous decisions</span>
          </button>
          <span className="qc-history-count">{selectedCode == null ? 'Select a product' : `Last ${Math.min(orderHistory.length, 25)} entries`}</span>
        </div>
        {historyOpen && (
        <div className="lo-scroll qc-history-scroll">
          <table className="lo-table lo-dense">
            <thead><tr><th>Product Name</th><th className="lo-num">Or Qty</th><th className="lo-num">Org Order</th><th className="lo-num">Pack</th><th className="lo-num">MRP</th><th>Remarks</th><th>Wanted Date</th><th>Wanted</th><th>Or Supplier</th></tr></thead>
            <tbody>
              {orderHistory.map((row, i) => (
                <tr key={i}><td><span className="qc-product-name" title={row.ProductName}>{row.ProductName}</span></td><td className="lo-num">{row.Orqty ?? '—'}</td><td className="lo-num">{row.OrgOrderQty ?? '—'}</td><td className="lo-num">{row.saleunit ?? '—'}</td><td className="lo-num">{row.MRP ?? '—'}</td><td>{row.remarks ?? '—'}</td><td>{fmtDate(row.Wanteddate)}</td><td>{row.WantedType ?? '—'}</td><td>{row.Orsupplier ?? '—'}</td></tr>
              ))}
              {!orderHistory.length && <tr><td colSpan={9} className="lo-empty">{selectedCode == null ? 'Select a product to see its previous-order history.' : 'No previous-order history for this product.'}</td></tr>}
            </tbody>
          </table>
        </div>
        )}
      </section>
    </div>
  )
}
