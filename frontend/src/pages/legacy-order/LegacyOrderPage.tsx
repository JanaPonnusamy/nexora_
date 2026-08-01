import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { legacyOrderService } from '../../services/legacyOrderService'
import type { LegacyJob, LegacyStore, OrderMode, OrderRow, PreviousOrder, PreviousOrderSupplier, SupplierComparisonProduct } from '../../types/legacyOrder'
import './legacy-order.css'

const POLL_MS = 1500
// The internal "HO" branch whose own stock feeds every other store's
// SupplierStock rows (Stock Update button). Matches dbo.Stores.StoreName.
const HO_STORE_NAME = 'NMW'

type StoreSettings = { minDays: number; maxDays: number; mode: OrderMode }

function fmtDateTime(value: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString()
}

export default function LegacyOrderPage() {
  const [stores, setStores] = useState<LegacyStore[]>([])
  const [settings, setSettings] = useState<Record<string, StoreSettings>>({})
  const [jobs, setJobs] = useState<Record<string, LegacyJob>>({})
  const [error, setError] = useState<string | null>(null)
  const [compareStore, setCompareStore] = useState('')
  const [previousOrders, setPreviousOrders] = useState<PreviousOrder[]>([])
  const [selectedOrderId, setSelectedOrderId] = useState('')
  const [suppliers, setSuppliers] = useState<PreviousOrderSupplier[]>([])
  const [selectedSupplier, setSelectedSupplier] = useState('')
  const [reviewProducts, setReviewProducts] = useState<SupplierComparisonProduct[]>([])
  const [reviewLoading, setReviewLoading] = useState(false)
  const [compareBusy, setCompareBusy] = useState(false)
  const [compareMessage, setCompareMessage] = useState('')
  const [gridStore, setGridStore] = useState('')
  const [gridRows, setGridRows] = useState<OrderRow[]>([])
  const [gridLoading, setGridLoading] = useState(false)
  const [gridEdits, setGridEdits] = useState<Record<number, number>>({})
  const [gridSaving, setGridSaving] = useState<number | null>(null)
  const [selectedProductCode, setSelectedProductCode] = useState<number | null>(null)
  const pollers = useRef(new Map<string, number>())

  useEffect(() => {
    Promise.all([legacyOrderService.listStores(), legacyOrderService.defaults()])
      .then(([storeList, defaults]) => {
        setStores(storeList)
        setSettings(Object.fromEntries(storeList.map((store) => [
          store.store_name,
          { minDays: defaults.min_days, maxDays: defaults.max_days, mode: 'local' as const },
        ])))
        if (storeList.length) {
          setCompareStore(storeList[0].store_name)
          setGridStore(storeList[0].store_name)
        }
      })
      .catch((e: Error) => setError(e.message))
  }, [])

  const updateJob = useCallback((job: LegacyJob) => {
    setJobs((current) => ({ ...current, [job.job_id]: job }))
    if (job.status !== 'running') {
      const poller = pollers.current.get(job.job_id)
      if (poller) window.clearInterval(poller)
      pollers.current.delete(job.job_id)
    }
  }, [])

  const watch = useCallback((jobId: string) => {
    const poll = () => legacyOrderService.getJob(jobId).then(updateJob).catch((e: Error) => {
      const poller = pollers.current.get(jobId)
      if (poller) window.clearInterval(poller)
      pollers.current.delete(jobId)
      setError(e.message)
    })
    void poll()
    pollers.current.set(jobId, window.setInterval(poll, POLL_MS))
  }, [updateJob])

  useEffect(() => () => {
    pollers.current.forEach((poller) => window.clearInterval(poller))
    pollers.current.clear()
  }, [])

  const start = (run: () => Promise<{ job_id: string }>) => {
    setError(null)
    run().then(({ job_id }) => watch(job_id)).catch((e: Error) => setError(e.message))
  }

  const runningFor = useCallback((storeName: string) =>
    Object.values(jobs).find((job) => job.store_name === storeName && job.status === 'running'), [jobs])

  const patchSettings = (storeName: string, patch: Partial<StoreSettings>) => {
    setSettings((current) => ({
      ...current,
      [storeName]: { ...current[storeName], ...patch },
    }))
  }

  useEffect(() => {
    if (!compareStore) return
    setPreviousOrders([])
    setSelectedOrderId('')
    setCompareMessage('')
    legacyOrderService.previousOrders(compareStore)
      .then((orders) => {
        setPreviousOrders(orders)
        if (orders.length) setSelectedOrderId(String(orders[0].order_id))
      })
      .catch((e: Error) => setError(e.message))
  }, [compareStore])

  useEffect(() => {
    if (!compareStore || !selectedOrderId) {
      setSuppliers([])
      setSelectedSupplier('')
      setReviewProducts([])
      return
    }
    legacyOrderService.previousOrderSuppliers(compareStore, Number(selectedOrderId))
      .then((rows) => {
        setSuppliers(rows)
        setSelectedSupplier('')
        setReviewProducts([])
      })
      .catch((e: Error) => setError(e.message))
  }, [compareStore, selectedOrderId])

  const compare = () => {
    if (!compareStore || !selectedOrderId) return
    setCompareBusy(true)
    setCompareMessage('')
    legacyOrderService.comparePreviousOrder(compareStore, Number(selectedOrderId))
      .then((result) => setCompareMessage(
        `Compared order ${result.order_id}. ${result.affected_rows} row updates applied.`,
      ))
      .catch((e: Error) => setError(e.message))
      .finally(() => setCompareBusy(false))
  }

  const compareSupplier = (supplierCode: string) => {
    if (!compareStore || !selectedOrderId) return
    setCompareBusy(true)
    setCompareMessage('')
    legacyOrderService.comparePreviousOrderSupplier(
      compareStore, Number(selectedOrderId), supplierCode,
    )
      .then((result) => setCompareMessage(
        `Compared supplier ${result.supplier_code}. ${result.affected_rows} row updates applied.`,
      ))
      .catch((e: Error) => setError(e.message))
      .finally(() => setCompareBusy(false))
  }

  const reviewSupplier = (supplierCode: string) => {
    setSelectedSupplier(supplierCode)
    setReviewProducts([])
    setReviewLoading(true)
    legacyOrderService.previousOrderSupplierProducts(
      compareStore, Number(selectedOrderId), supplierCode,
    )
      .then(setReviewProducts)
      .catch((e: Error) => setError(e.message))
      .finally(() => setReviewLoading(false))
  }

  const loadGrid = useCallback((storeName: string) => {
    if (!storeName) return
    setGridLoading(true)
    setGridEdits({})
    setSelectedProductCode(null)
    legacyOrderService.orders(storeName)
      .then(setGridRows)
      .catch((e: Error) => setError(e.message))
      .finally(() => setGridLoading(false))
  }, [])

  useEffect(() => {
    loadGrid(gridStore)
  }, [gridStore, loadGrid])

  const saveOrderQty = (productCode: number, orderQty: number) => {
    if (!gridStore) return
    setGridSaving(productCode)
    legacyOrderService.updateOrderQty(gridStore, productCode, orderQty)
      .then(() => {
        setGridRows((rows) => rows.map((row) => (
          row.ProductCode === productCode ? { ...row, OrderQty: orderQty } : row
        )))
        setGridEdits((edits) => {
          const next = { ...edits }
          delete next[productCode]
          return next
        })
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setGridSaving(null))
  }

  const sortedJobs = useMemo(() => Object.values(jobs).sort(
    (a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime(),
  ), [jobs])

  return (
    <div className="legacy-order">
      <header className="lo-header">
        <div>
          <h1>Legacy Order Console</h1>
          <p className="lo-sub">Run branch sync and order processing independently across multiple stores.</p>
        </div>
        <div className="lo-actions">
          <Link to="/legacy-order/qty-check" className="lo-btn"><i className="bi bi-table" /> Qty Check Grid</Link>
          <span className="lo-badge">Legacy DB</span>
        </div>
      </header>

      {error && <div className="lo-error" role="alert">{error}<button type="button" onClick={() => setError(null)} aria-label="Dismiss">×</button></div>}

      <section className="lo-card">
        <div className="lo-section-title">
          <div><h2>Store operations</h2><p className="lo-note">Order Process always runs a full sync first. Defaults: 13 min days / 18 max days.</p></div>
          <span className="lo-count">{stores.length} stores</span>
        </div>
        <div className="lo-store-scroll">
          <table className="lo-table lo-store-grid">
            <thead><tr><th>Store</th><th>Connection</th><th>Last sync</th><th>Min / Max</th><th>Source</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody>
              {stores.map((store) => {
                const config = settings[store.store_name] ?? { minDays: 13, maxDays: 18, mode: 'local' as const }
                const running = runningFor(store.store_name)
                const invalid = config.minDays <= 0 || config.maxDays <= 0 || config.minDays > config.maxDays
                return (
                  <tr key={store.store_name}>
                    <td><strong>{store.store_name}</strong><small className="lo-cell-sub">Code {store.store_code}</small></td>
                    <td>{store.server_name || '—'}<small className="lo-cell-sub">{store.database || '—'}</small></td>
                    <td>{fmtDateTime(store.last_sync_time)}{store.last_sync_status && <span className={`lo-chip lo-chip-${store.last_sync_status.toLowerCase()}`}>{store.last_sync_status}</span>}</td>
                    <td><div className="lo-inline-inputs"><input aria-label={`${store.store_name} minimum days`} type="number" min={1} value={config.minDays} onChange={(e) => patchSettings(store.store_name, { minDays: Number(e.target.value) })} /><span>/</span><input aria-label={`${store.store_name} maximum days`} type="number" min={1} value={config.maxDays} onChange={(e) => patchSettings(store.store_name, { maxDays: Number(e.target.value) })} /></div>{invalid && <small className="lo-invalid">Check range</small>}</td>
                    <td><select aria-label={`${store.store_name} order source`} value={config.mode} onChange={(e) => patchSettings(store.store_name, { mode: e.target.value as OrderMode })}><option value="local">Local copy</option><option value="remote">Remote live</option></select></td>
                    <td>{running ? <><span className="lo-running-dot" />{running.kind === 'sync' ? 'Syncing' : running.kind === 'order' ? 'Processing' : 'Updating stock'}<small className="lo-cell-sub">{running.message}</small></> : <span className="text-body-secondary">Ready</span>}</td>
                    <td><div className="lo-actions"><button type="button" className="lo-btn" disabled={Boolean(running)} onClick={() => start(() => legacyOrderService.startSync(store.store_name))}><i className="bi bi-arrow-repeat" /> Sync</button><button type="button" className="lo-btn lo-btn-primary" disabled={Boolean(running) || invalid} onClick={() => start(() => legacyOrderService.startOrderProcess(store.store_name, config.minDays, config.maxDays, config.mode))}><i className="bi bi-play-fill" /> Sync + Order</button>{store.store_name !== HO_STORE_NAME && <button type="button" className="lo-btn" disabled={Boolean(running)} title={`Push ${HO_STORE_NAME}'s stock into this store's supplier feed`} onClick={() => start(() => legacyOrderService.startStockUpdate(store.store_name, HO_STORE_NAME))}><i className="bi bi-cloud-arrow-up" /> Stock Update</button>}</div></td>
                  </tr>
                )
              })}
              {!stores.length && <tr><td colSpan={7} className="lo-empty">No active stores found.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      <div className="lo-lower-grid">
        <section className="lo-card">
          <div className="lo-section-title">
            <div><h2>Order grid</h2><p className="lo-note">Current OrderManagement rows for review. Set a product's Order Qty to 0 to mark it "no need" — it will be closed out on the next compare instead of reappearing.</p></div>
            <label className="lo-store-picker"><span>Store</span><select value={gridStore} onChange={(e) => setGridStore(e.target.value)}>{stores.map((store) => <option key={store.store_name} value={store.store_name}>{store.store_name}</option>)}</select></label>
          </div>
          <div className="lo-review-scroll">
            <table className="lo-table lo-review-table">
              <thead><tr><th>Product</th><th className="lo-num">Stock</th><th className="lo-num">Order Qty</th><th>Status</th></tr></thead>
              <tbody>
                {gridRows.map((row) => (
                  <tr
                    key={row.ProductCode}
                    className={selectedProductCode === row.ProductCode ? 'lo-supplier-row is-selected' : undefined}
                    onClick={() => setSelectedProductCode(row.ProductCode)}
                    style={{ cursor: 'pointer' }}
                  >
                    <td><strong>{row.ProductName}</strong><small className="lo-cell-sub">{row.ProductCode}</small></td>
                    <td className="lo-num">{row.TotalStock}</td>
                    <td className="lo-num">{gridEdits[row.ProductCode] ?? row.OrderQty}</td>
                    <td><span className={`lo-chip ${row.Status === 2 ? 'lo-chip-success' : 'lo-chip-running'}`}>{row.Status === 2 ? 'Closed' : 'Pending'}</span></td>
                  </tr>
                ))}
                {!gridRows.length && <tr><td colSpan={4} className="lo-empty">{gridLoading ? 'Loading order grid…' : 'No order rows for this store.'}</td></tr>}
              </tbody>
            </table>
          </div>
        </section>

        <section className="lo-card lo-activity">
          <div className="lo-section-title"><div><h2>Product detail</h2><p className="lo-note">Select a product from the grid to review and edit it.</p></div></div>
          {selectedProductCode !== null && (() => {
            const row = gridRows.find((r) => r.ProductCode === selectedProductCode)
            if (!row) return null
            const edited = gridEdits[row.ProductCode]
            const value = edited ?? row.OrderQty
            const dirty = edited !== undefined && edited !== row.OrderQty
            return (
              <div className="lo-product-review">
                <div className="lo-review-header">
                  <div><span className="lo-eyebrow">Order grid review</span><h3>{row.ProductName}</h3><p>{row.ProductCode} · {gridStore}</p></div>
                  <span className={`lo-chip ${row.Status === 2 ? 'lo-chip-success' : 'lo-chip-running'}`}>{row.Status === 2 ? 'Closed' : 'Pending'}</span>
                </div>
                <dl className="lo-meta" style={{ padding: '0.75rem' }}>
                  <div><dt>Stock</dt><dd>{row.TotalStock}</dd></div>
                  <div><dt>Min / Max</dt><dd>{row.MinQty} / {row.MaxQty}</dd></div>
                  <div><dt>Sale Unit</dt><dd>{row.SaleUnit}</dd></div>
                  <div><dt>Wanted Type</dt><dd>{row.WantedType || '—'}</dd></div>
                  <div><dt>Remarks</dt><dd>{row.Remarks ?? '—'}</dd></div>
                  <div>
                    <dt>Order Qty</dt>
                    <dd>
                      <input
                        type="number"
                        min={0}
                        aria-label={`${row.ProductName} order quantity`}
                        value={value}
                        onChange={(e) => setGridEdits((edits) => ({ ...edits, [row.ProductCode]: Number(e.target.value) }))}
                        style={{ width: '5rem' }}
                      />
                    </dd>
                  </div>
                </dl>
                <div className="lo-review-footer">
                  <div><strong>No need for this cycle?</strong><small>Set Order Qty to 0 and save to close it out without a supplier order.</small></div>
                  <button
                    type="button"
                    className="lo-btn lo-btn-primary"
                    disabled={!dirty || gridSaving === row.ProductCode}
                    onClick={() => saveOrderQty(row.ProductCode, value)}
                  >
                    {gridSaving === row.ProductCode ? 'Saving…' : 'Save'}
                  </button>
                </div>
              </div>
            )
          })()}
          {selectedProductCode === null && <div className="lo-empty">No product selected.</div>}
        </section>
      </div>

      <div className="lo-lower-grid">
        <section className="lo-card">
          <h2>Compare previous order</h2>
          <p className="lo-note">Uses the original VB.NET comparison rules. Recent two-day orders are shown first, with the latest five as fallback.</p>
          <div className="lo-compare-controls visually-hidden">
            <label><span>Store</span><select value={compareStore} onChange={(e) => setCompareStore(e.target.value)}>{stores.map((store) => <option key={store.store_name}>{store.store_name}</option>)}</select></label>
            <label className="lo-grow"><span>Previous order</span><select value={selectedOrderId} onChange={(e) => setSelectedOrderId(e.target.value)}><option value="">Select order</option>{previousOrders.map((order) => <option key={order.order_id} value={order.order_id}>#{order.order_id} — {fmtDateTime(order.wanted_date)}</option>)}</select></label>
            <button type="button" className="lo-btn lo-btn-primary" disabled={!selectedOrderId || compareBusy || Boolean(runningFor(compareStore))} onClick={compare}>{compareBusy ? 'Comparing…' : 'Compare Order'}</button>
          </div>
          <div className="lo-modern-compare">
            <label className="lo-store-picker"><span>Store</span><select value={compareStore} onChange={(e) => setCompareStore(e.target.value)}>{stores.map((store) => <option key={store.store_name}>{store.store_name}</option>)}</select></label>
            <div className="lo-compare-grid" role="listbox" aria-label="Previous orders">
              {previousOrders.map((order) => (
                <button type="button" role="option" aria-selected={selectedOrderId === String(order.order_id)} className={`lo-order-tile${selectedOrderId === String(order.order_id) ? ' is-selected' : ''}`} key={order.order_id} onClick={() => setSelectedOrderId(String(order.order_id))}>
                  <span className="lo-order-icon"><i className="bi bi-receipt" /></span>
                  <span><strong>Order #{order.order_id}</strong><small>{fmtDateTime(order.wanted_date)}</small></span>
                  <i className="bi bi-chevron-right" />
                </button>
              ))}
              {!previousOrders.length && <div className="lo-empty">No previous orders for this store.</div>}
            </div>
            {selectedOrderId && (
              <div className="lo-supplier-area">
                <div className="lo-compare-toolbar"><div><strong>Order #{selectedOrderId}</strong><small>{suppliers.length} suppliers available</small></div><button type="button" className="lo-btn" disabled={compareBusy || Boolean(runningFor(compareStore))} onClick={compare}>{compareBusy ? 'Comparing…' : 'Compare Entire Order'}</button></div>
                <div className="lo-supplier-grid">
                  <div className="lo-supplier-head"><span>Supplier</span><span>Products</span><span>Action</span></div>
                  {suppliers.map((supplier) => <button type="button" className={`lo-supplier-row${selectedSupplier === supplier.supplier_code ? ' is-selected' : ''}`} key={supplier.supplier_code} onClick={() => reviewSupplier(supplier.supplier_code)}><span><strong>{supplier.supplier_name}</strong><small>{supplier.supplier_code}</small></span><span className="lo-product-count">{supplier.product_count}</span><span className="lo-review-link">Review <i className="bi bi-arrow-right" /></span></button>)}
                  {!suppliers.length && <div className="lo-empty">No assigned suppliers in this backup order.</div>}
                </div>
              </div>
            )}
          </div>
          {compareMessage && <div className="lo-success"><i className="bi bi-check-circle" /> {compareMessage}</div>}
        </section>

        <section className="lo-card lo-activity">
          <div className="lo-section-title"><div><h2>Task log</h2><p className="lo-note">Live progress from every store task.</p></div><span className="lo-count">{sortedJobs.filter((job) => job.status === 'running').length} running</span></div>
          <div className="lo-job-list">
            {sortedJobs.map((job) => {
              const progress = job.total_steps ? Math.round((job.step / job.total_steps) * 100) : 0
              return <article className="lo-job" key={job.job_id}><div className="lo-job-head"><strong>{job.store_name} · {job.kind === 'sync' ? 'Sync' : job.kind === 'order' ? 'Order Process' : 'Stock Update'}</strong><span className={`lo-chip lo-chip-${job.status}`}>{job.status}</span></div><div className="lo-progress"><div className={`lo-progress-bar lo-progress-${job.status}`} style={{ width: `${progress}%` }} /></div><p>{job.message}</p>{job.error && <small className="lo-invalid">{job.error}</small>}<details className="lo-log"><summary>{job.log.length} log entries</summary><ol>{job.log.map((entry, index) => <li key={`${entry.at}-${index}`}><time>{entry.at.split('T')[1] ?? entry.at}</time>{entry.message}</li>)}</ol></details></article>
            })}
            {!sortedJobs.length && <div className="lo-empty">Start Sync or Order Process to see live task activity.</div>}
          </div>
          {selectedSupplier && (
            <div className="lo-product-review">
              <div className="lo-review-header">
                <div><span className="lo-eyebrow">Supplier comparison review</span><h3>{suppliers.find((supplier) => supplier.supplier_code === selectedSupplier)?.supplier_name ?? selectedSupplier}</h3><p>Order #{selectedOrderId} · {reviewProducts.length} products</p></div>
                <span className="lo-chip lo-chip-running">Review required</span>
              </div>
              <div className="lo-review-scroll">
                <table className="lo-table lo-review-table">
                  <thead><tr><th>Product</th><th className="lo-num">Previous qty</th><th className="lo-num">Current qty</th><th className="lo-num">Previous stock</th><th className="lo-num">Current stock</th><th>Result</th></tr></thead>
                  <tbody>
                    {reviewProducts.map((product) => {
                      const changed = product.PreviousOrderedQty !== product.CurrentOrderQty || product.PreviousStock !== product.CurrentStock
                      return <tr key={product.PreviousProductCode}><td><strong>{product.CurrentProductName ?? product.PreviousProductName}</strong><small className="lo-cell-sub">{product.PreviousProductCode}</small></td><td className="lo-num">{product.PreviousOrderedQty ?? '—'}</td><td className="lo-num">{product.CurrentOrderQty ?? '—'}</td><td className="lo-num">{product.PreviousStock ?? '—'}</td><td className="lo-num">{product.CurrentStock ?? '—'}</td><td><span className={`lo-chip ${changed ? 'lo-chip-partial' : 'lo-chip-success'}`}>{changed ? 'Changed' : 'Same'}</span></td></tr>
                    })}
                    {!reviewProducts.length && <tr><td colSpan={6} className="lo-empty">{reviewLoading ? 'Loading product comparison…' : 'No products available for review.'}</td></tr>}
                  </tbody>
                </table>
              </div>
              <div className="lo-review-footer"><div><strong>Review complete?</strong><small>This applies the VB.NET supplier comparison rules to these products.</small></div><button type="button" className="lo-btn lo-btn-primary" disabled={reviewLoading || !reviewProducts.length || compareBusy || Boolean(runningFor(compareStore))} onClick={() => compareSupplier(selectedSupplier)}>{compareBusy ? 'Comparing…' : `Compare ${reviewProducts.length} Products`}</button></div>
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
