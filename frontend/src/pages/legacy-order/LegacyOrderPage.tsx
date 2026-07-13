import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { legacyOrderService } from '../../services/legacyOrderService'
import type {
  LegacyJob,
  LegacyStore,
  LegacyTable,
  OrderMode,
  OrderRow,
} from '../../types/legacyOrder'
import './legacy-order.css'

const POLL_MS = 1500

function fmtDateTime(value: string | null): string {
  if (!value) return '—'
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString()
}

function num(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return Number.isInteger(value) ? String(value) : value.toFixed(2)
}

export default function LegacyOrderPage() {
  const [stores, setStores] = useState<LegacyStore[]>([])
  const [tables, setTables] = useState<LegacyTable[]>([])
  const [storeName, setStoreName] = useState('')
  const [error, setError] = useState<string | null>(null)

  // Sync panel
  const [selectedTables, setSelectedTables] = useState<Set<string>>(new Set())

  // Order panel — the legacy defaults, overridden by /defaults once loaded.
  const [minDays, setMinDays] = useState(15)
  const [maxDays, setMaxDays] = useState(20)
  const [mode, setMode] = useState<OrderMode>('local')

  const [job, setJob] = useState<LegacyJob | null>(null)
  const [busy, setBusy] = useState(false)

  const [orders, setOrders] = useState<OrderRow[]>([])
  const [ordersLoading, setOrdersLoading] = useState(false)
  const [wantedType, setWantedType] = useState('All')
  const [search, setSearch] = useState('')

  const pollRef = useRef<number | null>(null)

  const store = useMemo(
    () => stores.find((s) => s.store_name === storeName) ?? null,
    [stores, storeName],
  )

  useEffect(() => {
    Promise.all([
      legacyOrderService.listStores(),
      legacyOrderService.listTables(),
      legacyOrderService.defaults(),
    ])
      .then(([storeList, tableList, defaults]) => {
        setStores(storeList)
        setTables(tableList)
        setSelectedTables(new Set(tableList.map((t) => t.source)))
        setMinDays(defaults.min_days)
        setMaxDays(defaults.max_days)
        if (storeList.length) setStoreName(storeList[0].store_name)
      })
      .catch((e: Error) => setError(e.message))
  }, [])

  const loadOrders = useCallback((name: string) => {
    if (!name) return
    setOrdersLoading(true)
    legacyOrderService
      .orders(name)
      .then(setOrders)
      .catch((e: Error) => setError(e.message))
      .finally(() => setOrdersLoading(false))
  }, [])

  useEffect(() => {
    setOrders([])
    setWantedType('All')
    loadOrders(storeName)
  }, [storeName, loadOrders])

  // Poll the running job until it settles, then refresh the grid.
  const watch = useCallback(
    (jobId: string) => {
      if (pollRef.current) window.clearInterval(pollRef.current)
      pollRef.current = window.setInterval(() => {
        legacyOrderService
          .getJob(jobId)
          .then((next) => {
            setJob(next)
            if (next.status !== 'running') {
              if (pollRef.current) window.clearInterval(pollRef.current)
              pollRef.current = null
              setBusy(false)
              if (next.kind === 'order') loadOrders(next.store_name)
            }
          })
          .catch((e: Error) => {
            if (pollRef.current) window.clearInterval(pollRef.current)
            pollRef.current = null
            setBusy(false)
            setError(e.message)
          })
      }, POLL_MS)
    },
    [loadOrders],
  )

  useEffect(
    () => () => {
      if (pollRef.current) window.clearInterval(pollRef.current)
    },
    [],
  )

  const start = (run: () => Promise<{ job_id: string }>) => {
    setError(null)
    setJob(null)
    setBusy(true)
    run()
      .then(({ job_id }) => watch(job_id))
      .catch((e: Error) => {
        setBusy(false)
        setError(e.message)
      })
  }

  const onSync = () =>
    start(() =>
      legacyOrderService.startSync(storeName, Array.from(selectedTables)),
    )

  const onOrderProcess = () =>
    start(() =>
      legacyOrderService.startOrderProcess(storeName, minDays, maxDays, mode),
    )

  const toggleTable = (source: string) => {
    setSelectedTables((prev) => {
      const next = new Set(prev)
      if (next.has(source)) next.delete(source)
      else next.add(source)
      return next
    })
  }

  const wantedTypes = useMemo(() => {
    const set = new Set(orders.map((o) => o.WantedType).filter(Boolean))
    return ['All', ...Array.from(set).sort()]
  }, [orders])

  const visibleOrders = useMemo(() => {
    const q = search.trim().toLowerCase()
    return orders.filter((o) => {
      if (wantedType !== 'All' && o.WantedType !== wantedType) return false
      if (!q) return true
      return (
        (o.ProductName ?? '').toLowerCase().includes(q) ||
        String(o.ProductCode).includes(q)
      )
    })
  }, [orders, wantedType, search])

  const progressPct = job && job.total_steps
    ? Math.round((job.step / job.total_steps) * 100)
    : 0

  const canRun = Boolean(storeName) && !busy

  return (
    <div className="legacy-order">
      <header className="lo-header">
        <div>
          <h1>Legacy Order Console</h1>
          <p className="lo-sub">
            Web trigger for the VB.NET OrderManagement app. Reads and writes the
            old <strong>OrderNMC</strong> database and the branch servers it points
            at — not the Nexora platform tables.
          </p>
        </div>
        <span className="lo-badge">Legacy DB</span>
      </header>

      {error && (
        <div className="lo-error" role="alert">
          {error}
          <button type="button" onClick={() => setError(null)} aria-label="Dismiss">
            ×
          </button>
        </div>
      )}

      <section className="lo-card">
        <h2>Store</h2>
        <div className="lo-row">
          <label>
            <span>Store name</span>
            <select
              value={storeName}
              onChange={(e) => setStoreName(e.target.value)}
              disabled={busy}
            >
              {stores.map((s) => (
                <option key={s.store_name} value={s.store_name}>
                  {s.store_name} ({s.store_code})
                </option>
              ))}
            </select>
          </label>
          {store && (
            <dl className="lo-meta">
              <div>
                <dt>Source server</dt>
                <dd>{store.server_name || '—'}</dd>
              </div>
              <div>
                <dt>Database</dt>
                <dd>{store.database || '—'}</dd>
              </div>
              <div>
                <dt>Last sync</dt>
                <dd>
                  {fmtDateTime(store.last_sync_time)}
                  {store.last_sync_status && (
                    <span
                      className={`lo-chip lo-chip-${store.last_sync_status.toLowerCase()}`}
                    >
                      {store.last_sync_status}
                    </span>
                  )}
                </dd>
              </div>
            </dl>
          )}
        </div>
      </section>

      <div className="lo-grid">
        <section className="lo-card">
          <h2>Sync</h2>
          <p className="lo-note">
            Pulls each table from the branch server into OrderNMC, stamped with the
            store name. Incremental by max ID; staged and merged per table.
          </p>
          <ul className="lo-tables">
            {tables.map((t) => (
              <li key={t.source}>
                <label>
                  <input
                    type="checkbox"
                    checked={selectedTables.has(t.source)}
                    onChange={() => toggleTable(t.source)}
                    disabled={busy}
                  />
                  <span>{t.source}</span>
                  {t.source !== t.destination && (
                    <em className="lo-dest">→ {t.destination}</em>
                  )}
                </label>
              </li>
            ))}
          </ul>
          <button
            type="button"
            className="lo-btn lo-btn-primary"
            onClick={onSync}
            disabled={!canRun || selectedTables.size === 0}
          >
            Sync {selectedTables.size} table{selectedTables.size === 1 ? '' : 's'}
          </button>
        </section>

        <section className="lo-card">
          <h2>Order Process</h2>
          <p className="lo-note">
            Runs the 90-day min/max order query, backs up the store&apos;s current
            OrderManagement rows, then rewrites them and stamps an order header.
          </p>
          <div className="lo-row">
            <label>
              <span>Min days</span>
              <input
                type="number"
                min={1}
                value={minDays}
                onChange={(e) => setMinDays(Number(e.target.value))}
                disabled={busy}
              />
            </label>
            <label>
              <span>Max days</span>
              <input
                type="number"
                min={1}
                value={maxDays}
                onChange={(e) => setMaxDays(Number(e.target.value))}
                disabled={busy}
              />
            </label>
          </div>
          <fieldset className="lo-modes" disabled={busy}>
            <legend>Source</legend>
            <label>
              <input
                type="radio"
                name="lo-mode"
                checked={mode === 'local'}
                onChange={() => setMode('local')}
              />
              <span>
                Local <em>— OrderNMC&apos;s synced copy</em>
              </span>
            </label>
            <label>
              <input
                type="radio"
                name="lo-mode"
                checked={mode === 'remote'}
                onChange={() => setMode('remote')}
              />
              <span>
                Remote <em>— branch server, live</em>
              </span>
            </label>
          </fieldset>
          <button
            type="button"
            className="lo-btn lo-btn-primary"
            onClick={onOrderProcess}
            disabled={!canRun || minDays > maxDays}
          >
            Process Order
          </button>
          {minDays > maxDays && (
            <p className="lo-warn">Min days cannot be greater than max days.</p>
          )}
        </section>
      </div>

      {job && (
        <section className="lo-card">
          <h2>
            {job.kind === 'sync' ? 'Sync' : 'Order Process'} — {job.store_name}
            <span className={`lo-chip lo-chip-${job.status}`}>{job.status}</span>
          </h2>
          <div className="lo-progress">
            <div
              className={`lo-progress-bar lo-progress-${job.status}`}
              style={{ width: `${progressPct}%` }}
            />
          </div>
          <p className="lo-status">{job.message}</p>

          {job.error && <p className="lo-warn">{job.error}</p>}

          {job.result?.tables && (
            <table className="lo-table">
              <thead>
                <tr>
                  <th>Table</th>
                  <th>Destination</th>
                  <th className="lo-num">Rows</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {job.result.tables.map((t) => (
                  <tr key={t.table}>
                    <td>{t.table}</td>
                    <td>{t.destination}</td>
                    <td className="lo-num">{t.rows}</td>
                    <td>
                      <span className={`lo-chip lo-chip-${t.status}`}>{t.status}</span>
                      {t.error && <span className="lo-errtext">{t.error}</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {job.result?.header && (
            <dl className="lo-meta">
              <div>
                <dt>Order ID</dt>
                <dd>{job.result.header.order_id}</dd>
              </div>
              <div>
                <dt>Order no.</dt>
                <dd>{job.result.header.order_no}</dd>
              </div>
              <div>
                <dt>Last GRN</dt>
                <dd>{job.result.header.last_grn || '—'}</dd>
              </div>
              <div>
                <dt>Last sale bill</dt>
                <dd>{job.result.header.last_sale_bill_no || '—'}</dd>
              </div>
            </dl>
          )}

          <details className="lo-log">
            <summary>Log ({job.log.length})</summary>
            <ol>
              {job.log.map((entry, i) => (
                <li key={`${entry.at}-${i}`}>
                  <time>{entry.at.split('T')[1] ?? entry.at}</time>
                  {entry.message}
                </li>
              ))}
            </ol>
          </details>
        </section>
      )}

      <section className="lo-card">
        <h2>
          Order Management — {storeName || '—'}
          <span className="lo-count">
            {visibleOrders.length}
            {visibleOrders.length !== orders.length && ` of ${orders.length}`} rows
          </span>
        </h2>
        <div className="lo-row">
          <label>
            <span>Wanted type</span>
            <select
              value={wantedType}
              onChange={(e) => setWantedType(e.target.value)}
            >
              {wantedTypes.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </label>
          <label className="lo-grow">
            <span>Search</span>
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Product name or code"
            />
          </label>
          <button
            type="button"
            className="lo-btn"
            onClick={() => loadOrders(storeName)}
            disabled={!storeName || ordersLoading}
          >
            Refresh
          </button>
        </div>

        <div className="lo-scroll">
          <table className="lo-table">
            <thead>
              <tr>
                <th>Code</th>
                <th>Product</th>
                <th className="lo-num">Stock</th>
                <th className="lo-num">Sales (90d)</th>
                <th className="lo-num">Min</th>
                <th className="lo-num">Max</th>
                <th className="lo-num">Order qty</th>
                <th>Wanted type</th>
                <th>Type</th>
                <th className="lo-num">Freq</th>
              </tr>
            </thead>
            <tbody>
              {visibleOrders.map((o, i) => (
                <tr key={`${o.ProductCode}-${i}`}>
                  <td>{o.ProductCode}</td>
                  <td>{o.ProductName}</td>
                  <td className="lo-num">{num(o.TotalStock)}</td>
                  <td className="lo-num">{num(o.SLSQty)}</td>
                  <td className="lo-num">{num(o.MinQty)}</td>
                  <td className="lo-num">{num(o.MaxQty)}</td>
                  <td className="lo-num lo-strong">{num(o.OrderQty)}</td>
                  <td>{o.WantedType}</td>
                  <td>{o.ProductTypeName}</td>
                  <td className="lo-num">{num(o.Frequence)}</td>
                </tr>
              ))}
              {!visibleOrders.length && (
                <tr>
                  <td colSpan={10} className="lo-empty">
                    {ordersLoading
                      ? 'Loading…'
                      : orders.length
                        ? 'No rows match the current filter.'
                        : 'No order rows for this store yet. Run Order Process.'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
