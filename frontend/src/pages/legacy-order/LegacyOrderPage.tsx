import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { legacyOrderService } from '../../services/legacyOrderService'
import type { LegacyDbHealth, LegacyDbRecovery, LegacyJob, LegacyStore, OrderMode, PreviousOrder, PreviousOrderSupplier, SupplierComparisonProduct } from '../../types/legacyOrder'
import './legacy-order.css'
import { FilterBar, FilterSearch, FilterSelect } from '../../design-system/components/FilterBar'

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
  const [orderSearch, setOrderSearch] = useState('')
  const [settingsOpenFor, setSettingsOpenFor] = useState<string | null>(null)
  const [infoOpenFor, setInfoOpenFor] = useState<string | null>(null)
  const [dbHealth, setDbHealth] = useState<LegacyDbHealth | null>(null)
  const [dbBusy, setDbBusy] = useState<'' | 'check' | 'recover' | 'repair'>('')
  const [recovery, setRecovery] = useState<LegacyDbRecovery | null>(null)
  const pollers = useRef(new Map<string, number>())

  const loadStores = useCallback(() =>
    Promise.all([legacyOrderService.listStores(), legacyOrderService.defaults()])
      .then(([storeList, defaults]) => {
        setStores(storeList)
        setSettings(Object.fromEntries(storeList.map((store) => [
          store.store_name,
          { minDays: defaults.min_days, maxDays: defaults.max_days, mode: 'local' as const },
        ])))
        setCompareStore((current) => current || (storeList[0]?.store_name ?? ''))
      }), [])

  // Read DB state without changing it. On success (DB healthy) reload the stores
  // and clear the outage banner; on failure surface it so the recovery card shows.
  const checkHealth = useCallback((silent = false): Promise<LegacyDbHealth | null> => {
    if (!silent) setDbBusy('check')
    return legacyOrderService.dbHealth()
      .then((health) => {
        setDbHealth(health)
        if (health.online) {
          setError(null)
          void loadStores()
        }
        return health
      })
      .catch((e: Error) => { if (!silent) setError(e.message); return null })
      .finally(() => { if (!silent) setDbBusy('') })
  }, [loadStores])

  useEffect(() => {
    loadStores().catch((e: Error) => {
      setError(e.message)
      void checkHealth(true)
    })
  }, [loadStores, checkHealth])

  const runRecovery = (mode: 'recover' | 'repair') => {
    if (mode === 'repair' && !window.confirm(
      'Emergency Repair runs DBCC CHECKDB with REPAIR_ALLOW_DATA_LOSS. It can permanently '
      + 'delete corrupt rows/pages to bring the database back online. This is a last resort — continue?',
    )) return
    setDbBusy(mode)
    setRecovery(null)
    setError(null)
    const call = mode === 'repair'
      ? legacyOrderService.dbEmergencyRepair()
      : legacyOrderService.dbRecover()
    call
      .then((result) => {
        setRecovery(result)
        return checkHealth(true)
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setDbBusy(''))
  }

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

  const sortedJobs = useMemo(() => Object.values(jobs).sort(
    (a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime(),
  ), [jobs])

  const filteredOrders = useMemo(() => {
    const term = orderSearch.trim().toLowerCase()
    if (!term) return previousOrders
    return previousOrders.filter((order) => String(order.order_id).includes(term))
  }, [previousOrders, orderSearch])

  const healthyCount = stores.filter((store) => (store.last_sync_status ?? '').toLowerCase() === 'success').length
  const failedCount = stores.filter((store) => (store.last_sync_status ?? '').toLowerCase() === 'failed').length
  const runningCount = sortedJobs.filter((job) => job.status === 'running').length
  const lastGlobalSync = stores.reduce<string | null>((latest, store) => {
    if (!store.last_sync_time) return latest
    if (!latest || new Date(store.last_sync_time) > new Date(latest)) return store.last_sync_time
    return latest
  }, null)

  const infoStore = infoOpenFor ? stores.find((store) => store.store_name === infoOpenFor) : undefined
  const infoJob = infoOpenFor ? runningFor(infoOpenFor) ?? sortedJobs.find((job) => job.store_name === infoOpenFor) : undefined

  return (
    <div className="legacy-order">
      <header className="lo-header">
        <div>
          <h1>Legacy Order Console</h1>
          <div className="lo-kpis">
            <span>{stores.length} Stores</span>
            <span className="lo-kpi-ok"><span className="lo-dot lo-dot-ok" />{healthyCount} Healthy</span>
            <span className="lo-kpi-fail"><span className="lo-dot lo-dot-fail" />{failedCount} Failed</span>
            <span className="lo-kpi-run"><span className="lo-dot lo-dot-run" />{runningCount} Running</span>
            <span className="lo-kpi-sync">Last sync {fmtDateTime(lastGlobalSync)}</span>
          </div>
        </div>
        <div className="lo-actions">
          <Link to="/legacy-order/workspace" className="lo-btn lo-btn-primary"><i className="bi bi-grid-3x3-gap" /> Order Workspace</Link>
          <span className="lo-badge">Legacy DB</span>
        </div>
      </header>

      {error && <div className="lo-error" role="alert">{error}<button type="button" onClick={() => setError(null)} aria-label="Dismiss">×</button></div>}

      {((dbHealth && !dbHealth.online) || recovery) && (
        <section className={`lo-db-recovery${dbHealth?.online ? ' is-online' : ''}`} role="region" aria-label="Legacy database recovery">
          <div className="lo-db-recovery-head">
            <div>
              {dbHealth?.online
                ? <strong><i className="bi bi-database-check" /> Legacy database is back online ({dbHealth.state} / {dbHealth.access})</strong>
                : <strong><i className="bi bi-database-exclamation" /> Legacy database {dbHealth?.state ? `is ${dbHealth.state}` : 'unavailable'}{dbHealth?.access ? ` / ${dbHealth.access}` : ''}</strong>}
              <p className="lo-note">{dbHealth?.message}</p>
            </div>
            <div className="lo-db-recovery-actions">
              <button type="button" className="lo-btn" disabled={Boolean(dbBusy)} onClick={() => { if (dbHealth?.online) setRecovery(null); void checkHealth() }}>
                <i className="bi bi-arrow-repeat" /> {dbBusy === 'check' ? 'Checking…' : dbHealth?.online ? 'Dismiss' : 'Recheck'}
              </button>
              {!dbHealth?.online && (
                <button type="button" className="lo-btn lo-btn-primary" disabled={Boolean(dbBusy)} title="Non-destructive: flips single-user back to multi-user or restarts crash recovery. Never loses data." onClick={() => runRecovery('recover')}>
                  <i className="bi bi-bandaid" /> {dbBusy === 'recover' ? 'Recovering…' : 'Auto Recover'}
                </button>
              )}
              {!dbHealth?.online && (
                <button type="button" className="lo-btn lo-btn-danger" disabled={Boolean(dbBusy)} title="Last resort: EMERGENCY + DBCC CHECKDB REPAIR_ALLOW_DATA_LOSS. Can permanently lose data." onClick={() => runRecovery('repair')}>
                  <i className="bi bi-exclamation-octagon" /> {dbBusy === 'repair' ? 'Repairing…' : 'Emergency Repair'}
                </button>
              )}
            </div>
          </div>
          {recovery && (
            <div className={`lo-db-recovery-result ${recovery.ok ? 'is-ok' : 'is-fail'}`}>
              <p><i className={`bi ${recovery.ok ? 'bi-check-circle' : 'bi-exclamation-triangle'}`} /> {recovery.message}</p>
              {recovery.steps.length > 0 && (
                <ol className="lo-db-steps">
                  {recovery.steps.map((step, index) => (
                    <li key={`${step.action}-${index}`} className={step.ok ? 'is-ok' : 'is-fail'}>
                      <i className={`bi ${step.ok ? 'bi-check-lg' : 'bi-x-lg'}`} />
                      <span>{step.action}</span>
                      {step.detail && <small>{step.detail}</small>}
                    </li>
                  ))}
                </ol>
              )}
            </div>
          )}
        </section>
      )}

      <section className="lo-card">
        <div className="lo-section-title">
          <div><h2>Store operations</h2><p className="lo-note">Process runs Sync → Order → Stock automatically. Defaults: 13 min days / 18 max days.</p></div>
        </div>
        <div className="lo-store-cards">
          {stores.map((store) => {
            const config = settings[store.store_name] ?? { minDays: 13, maxDays: 18, mode: 'local' as const }
            const running = runningFor(store.store_name)
            const invalid = config.minDays <= 0 || config.maxDays <= 0 || config.minDays > config.maxDays
            const failed = (store.last_sync_status ?? '').toLowerCase() === 'failed'
            const dotClass = running ? 'lo-dot-run' : failed ? 'lo-dot-fail' : 'lo-dot-ok'
            const lastJob = sortedJobs.find((job) => job.store_name === store.store_name && job.status !== 'running')
            const cardState = running ? 'running' : lastJob?.status === 'failed' ? 'failed' : lastJob?.status === 'completed' ? 'completed' : 'idle'
            return (
              <article className="lo-op-card" key={store.store_name} data-state={cardState}>
                <div className="lo-op-head">
                  <span className={`lo-dot ${dotClass}`} />
                  <strong>{store.store_name}</strong>
                  <span className="lo-op-icons">
                    <button type="button" className="lo-icon-btn" title="Processing settings" aria-label={`${store.store_name} settings`} onClick={() => setSettingsOpenFor(settingsOpenFor === store.store_name ? null : store.store_name)}><i className="bi bi-gear" /></button>
                    <button type="button" className="lo-icon-btn" title="Store information" aria-label={`${store.store_name} info`} onClick={() => setInfoOpenFor(store.store_name)}><i className="bi bi-info-circle" /></button>
                  </span>
                </div>
                <p className="lo-op-owner">{store.database || '—'}</p>
                <small className="lo-op-conn">{store.server_name || '—'}</small>

                {settingsOpenFor === store.store_name && (
                  <div className="lo-op-settings">
                    <label><span>Min days</span><input aria-label={`${store.store_name} minimum days`} type="number" min={1} value={config.minDays} onChange={(e) => patchSettings(store.store_name, { minDays: Number(e.target.value) })} /></label>
                    <label><span>Max days</span><input aria-label={`${store.store_name} maximum days`} type="number" min={1} value={config.maxDays} onChange={(e) => patchSettings(store.store_name, { maxDays: Number(e.target.value) })} /></label>
                    <label><span>Source</span><select aria-label={`${store.store_name} order source`} value={config.mode} onChange={(e) => patchSettings(store.store_name, { mode: e.target.value as OrderMode })}><option value="local">Local copy</option><option value="remote">Remote live</option></select></label>
                    {invalid && <small className="lo-invalid">Min must be ≤ max</small>}
                    <div className="lo-op-settings-actions">
                      <button type="button" className="lo-btn" onClick={() => { patchSettings(store.store_name, { minDays: 13, maxDays: 18, mode: 'local' }) }}>Reset default</button>
                      <button type="button" className="lo-btn" disabled={Boolean(running)} onClick={() => start(() => legacyOrderService.startSync(store.store_name))}><i className="bi bi-arrow-repeat" /> Sync only</button>
                      {store.store_name !== HO_STORE_NAME && <button type="button" className="lo-btn" disabled={Boolean(running)} title={`Push ${HO_STORE_NAME}'s stock into this store's supplier feed`} onClick={() => start(() => legacyOrderService.startStockUpdate(store.store_name, HO_STORE_NAME))}><i className="bi bi-cloud-arrow-up" /> Stock update only</button>}
                    </div>
                  </div>
                )}

                {running ? (
                  <div className="lo-op-progress">
                    <div className="lo-op-stepper">
                      <span className={running.kind !== undefined ? 'is-done' : ''}>Sync</span>
                      <span className={running.kind === 'order' || running.kind === 'stock' ? 'is-done' : running.kind === 'sync' ? 'is-active' : ''}>Order</span>
                      <span className={running.kind === 'stock' ? 'is-active' : ''}>Stock</span>
                    </div>
                    <small className="lo-cell-sub">{running.message}</small>
                    <button type="button" className="lo-btn lo-op-process" disabled><i className="bi bi-hourglass-split" /> Processing…</button>
                  </div>
                ) : (
                  <button type="button" className={`lo-btn lo-btn-primary lo-op-process${failed ? ' lo-op-retry' : ''}`} disabled={invalid} onClick={() => start(() => legacyOrderService.startOrderProcess(store.store_name, config.minDays, config.maxDays, config.mode))}>
                    <i className={`bi ${failed ? 'bi-arrow-clockwise' : 'bi-play-fill'}`} /> {failed ? 'Retry' : 'Process'}
                  </button>
                )}
              </article>
            )
          })}
          {!stores.length && <div className="lo-empty">No active stores found.</div>}
        </div>
      </section>

      {infoStore && (
        <div className="lo-drawer-backdrop" role="presentation" onClick={() => setInfoOpenFor(null)}>
          <aside className="lo-drawer" role="dialog" aria-label={`${infoStore.store_name} information`} onClick={(e) => e.stopPropagation()}>
            <div className="lo-drawer-head">
              <h3>Store information — {infoStore.store_name}</h3>
              <button type="button" className="lo-icon-btn" aria-label="Close" onClick={() => setInfoOpenFor(null)}>×</button>
            </div>
            <div className="lo-drawer-body">
              <h4>Last operation</h4>
              <dl className="lo-meta">
                <div><dt>Status</dt><dd>{infoJob ? <span className={`lo-chip lo-chip-${infoJob.status}`}>{infoJob.status}</span> : (infoStore.last_sync_status ?? '—')}</dd></div>
                <div><dt>Started</dt><dd>{infoJob ? fmtDateTime(infoJob.started_at) : '—'}</dd></div>
                <div><dt>Completed</dt><dd>{infoJob?.finished_at ? fmtDateTime(infoJob.finished_at) : '—'}</dd></div>
                <div><dt>Message</dt><dd>{infoJob?.message ?? '—'}</dd></div>
              </dl>
              <h4>Connection</h4>
              <dl className="lo-meta">
                <div><dt>Server</dt><dd>{infoStore.server_name || '—'}</dd></div>
                <div><dt>Database</dt><dd>{infoStore.database || '—'}</dd></div>
                <div><dt>Store code</dt><dd>{infoStore.store_code}</dd></div>
                <div><dt>Last sync</dt><dd>{fmtDateTime(infoStore.last_sync_time)}</dd></div>
              </dl>
              {infoJob?.result?.tables && infoJob.result.tables.length > 0 && (
                <>
                  <h4>Sync tables</h4>
                  <table className="lo-table">
                    <thead><tr><th>Table</th><th className="lo-num">Rows</th><th>Status</th></tr></thead>
                    <tbody>
                      {infoJob.result.tables.map((t) => (
                        <tr key={t.table}><td>{t.table}</td><td className="lo-num">{t.rows}</td><td><span className={`lo-chip lo-chip-${t.status}`}>{t.status}</span></td></tr>
                      ))}
                    </tbody>
                  </table>
                </>
              )}
              {infoJob?.log && infoJob.log.length > 0 && (
                <>
                  <h4>Log</h4>
                  <ol className="lo-drawer-log">
                    {infoJob.log.map((entry, index) => <li key={`${entry.at}-${index}`}><time>{entry.at.split('T')[1] ?? entry.at}</time>{entry.message}</li>)}
                  </ol>
                </>
              )}
            </div>
          </aside>
        </div>
      )}

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
            <FilterBar compact className="lo-compare-toprow" ariaLabel="Previous order filters">
              <FilterSelect label="Store" ariaLabel="Store" value={compareStore} onChange={setCompareStore}>
                {stores.map((store) => <option key={store.store_name}>{store.store_name}</option>)}
              </FilterSelect>
              <FilterSearch value={orderSearch} placeholder="Search order #" ariaLabel="Search previous orders" onChange={setOrderSearch} />
            </FilterBar>
            <div className="lo-compare-grid" role="listbox" aria-label="Previous orders">
              {filteredOrders.map((order) => (
                <button type="button" role="option" aria-selected={selectedOrderId === String(order.order_id)} className={`lo-order-tile${selectedOrderId === String(order.order_id) ? ' is-selected' : ''}`} key={order.order_id} onClick={() => setSelectedOrderId(String(order.order_id))}>
                  <span className="lo-order-icon"><i className="bi bi-receipt" /></span>
                  <span><strong>#{order.order_id}</strong><small>{fmtDateTime(order.wanted_date)}</small></span>
                  <i className="bi bi-chevron-right" />
                </button>
              ))}
              {!filteredOrders.length && <div className="lo-empty">No previous orders match.</div>}
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
