import { useCallback, useEffect, useRef, useState } from 'react'
import { legacyOrderService } from '../../services/legacyOrderService'
import { ApiError } from '../../services/apiClient'
import type {
  LegacyStore,
  OrderWorkflowStatus,
  PmOrderEntryRecent,
  PmOrderEntryState,
  PmOrderQueueRow,
} from '../../types/legacyOrder'
import { fmtDate, fmtMoney, fmtQty } from './format'
import './pm-order-entry.css'

const POLL_MS = 3000

const STATUS_LABEL: Record<string, string> = {
  QTY_REVIEW: 'Qty review pending',
  SUPPLIER_ASSIGNMENT: 'Supplier assignment pending',
  READY: 'Ready to finalize',
  FINALIZED: 'Finalized',
  DRAFT: 'Draft',
}

function fmtStamp(value: string | null | undefined): string {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  return d
    .toLocaleString('en-GB', { day: '2-digit', month: '2-digit', hour: 'numeric', minute: '2-digit', hour12: true })
    .replace(/\b([ap])m\b/gi, (s) => s.toUpperCase())
}

function errorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message
  if (err instanceof Error) return err.message
  return fallback
}

/** Two plain verification grids -- most recent GRNs and most recent sale
 *  bills, newest first, no exclusion filtering (see backend repository.
 *  recent_grns/recent_sale_bills). The PM reviews these against their own
 *  physical paperwork; the top row of each is what gets auto-submitted as
 *  Last GRN / Last bill. Replaces the old "received, not ordered" report,
 *  which answered a different question and confused the PM when its number
 *  disagreed with the Current Order card's own Last GRN. */
function RecentVerificationGrids({
  store,
  reloadToken,
  onTopRow,
}: {
  store: string
  reloadToken: number
  onTopRow: (topBill: string | null, topGrn: string | null) => void
}) {
  const [data, setData] = useState<PmOrderEntryRecent | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const storeRef = useRef(store)
  storeRef.current = store

  // Clear the grids the instant the store changes, instead of leaving the
  // previous store's rows (and its "will be used" top row) on screen until
  // the new fetch resolves -- a stale GRN/bill list under a different
  // store name is actively misleading, not just a cosmetic lag.
  useEffect(() => {
    setData(null)
    onTopRow(null, null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [store])

  const load = useCallback(() => {
    if (!store) return
    const requestedStore = store
    setLoading(true)
    setError('')
    legacyOrderService
      .pmOrderEntryRecent(store)
      .then((result) => {
        // The store may have changed again while this request was in
        // flight; a late response for an old store must not clobber the
        // grids the PM is now looking at.
        if (requestedStore !== storeRef.current) return
        setData(result)
        onTopRow(result.bills[0]?.bill_no ?? null, result.grns[0] ? String(result.grns[0].grn_no) : null)
      })
      .catch((err: unknown) => setError(errorMessage(err, 'Could not load the recent GRN/bill grids.')))
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [store])

  // reloadToken bumps once a triggered sync has finished, so the grids pick
  // up the freshly-synced GRN/bill rows without the PM doing anything else.
  useEffect(() => {
    load()
  }, [load, reloadToken])

  const grns = data?.grns ?? []
  const bills = data?.bills ?? []

  return (
    <div className="poe-grid">
      <section className="poe-card">
        <header className="poe-card-head">
          <h3>Recent GRNs</h3>
          <span className="poe-muted">Most recent supplier GRNs · as of the last sync</span>
          <div className="poe-tools">
            <button type="button" className="secondary-button" onClick={load} disabled={loading}>
              {loading ? 'Loading…' : 'Refresh'}
            </button>
          </div>
        </header>
        {error && <div className="status-line error">{error}</div>}
        <div className="poe-tablewrap">
          <table className="poe-table">
            <thead>
              <tr>
                <th>GRN#</th>
                <th>Date</th>
                <th className="poe-left">Supplier</th>
                <th>Items</th>
                <th>Total qty</th>
                <th title="Real GRN entry time where available; falls back to when this GRN reached the server via sync for rows synced before this column existed.">
                  Time
                </th>
              </tr>
            </thead>
            <tbody>
              {grns.map((r, i) => (
                <tr key={`${r.grn_no}-${i}`} className={i === 0 ? 'poe-top-row' : undefined}>
                  <td>
                    {r.grn_no}
                    {i === 0 && <span className="poe-top-badge">Will be used</span>}
                  </td>
                  <td>{fmtDate(r.grn_date)}</td>
                  <td className="poe-left">{r.supplier_name || r.supplier_code || '—'}</td>
                  <td>{r.item_count}</td>
                  <td>{fmtQty(r.total_qty)}</td>
                  <td>
                    {r.grn_time ? fmtStamp(r.grn_time) : <>{fmtStamp(r.synced_at)} <span className="poe-auto-tag">(synced)</span></>}
                  </td>
                </tr>
              ))}
              {!loading && !grns.length && (
                <tr>
                  <td colSpan={6} className="poe-muted">
                    No GRNs found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="poe-muted">
          {grns.length} GRN{grns.length === 1 ? '' : 's'}
        </div>
      </section>

      <section className="poe-card">
        <header className="poe-card-head">
          <h3>Recent sale bills</h3>
          <span className="poe-muted">Most recent sale bills · as of the last sync</span>
        </header>
        <div className="poe-tablewrap">
          <table className="poe-table">
            <thead>
              <tr>
                <th>Bill#</th>
                <th>Date / time</th>
                <th className="poe-left">Salesman</th>
                <th className="poe-left">Customer</th>
                <th>Amount</th>
              </tr>
            </thead>
            <tbody>
              {bills.map((r, i) => (
                <tr key={`${r.bill_no}-${i}`} className={i === 0 ? 'poe-top-row' : undefined}>
                  <td>
                    {r.bill_no || '—'}
                    {i === 0 && <span className="poe-top-badge">Will be used</span>}
                  </td>
                  <td>{fmtStamp(r.bill_date)}</td>
                  <td className="poe-left">{r.salesman || '—'}</td>
                  <td className="poe-left">{r.customer || '—'}</td>
                  <td>{fmtMoney(r.amount)}</td>
                </tr>
              ))}
              {!loading && !bills.length && (
                <tr>
                  <td colSpan={5} className="poe-muted">
                    No sale bills found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="poe-muted">
          {bills.length} line{bills.length === 1 ? '' : 's'}
        </div>
      </section>
    </div>
  )
}

interface SyncLogLine {
  stamp: string
  text: string
}

function fmtLogStamp(d: Date): string {
  return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export default function PmOrderEntryPage() {
  const [stores, setStores] = useState<LegacyStore[]>([])
  const [lastSync, setLastSync] = useState<Record<string, string | null>>({})
  const [store, setStore] = useState('')
  const [state, setState] = useState<PmOrderEntryState | null>(null)
  // Auto-filled from the top row of the recent-GRN / recent-bill grids --
  // the PM never types these (owner ruling 2026-11-24: "pm user dont want to
  // know exactly what they doing").
  const [topBill, setTopBill] = useState<string | null>(null)
  const [topGrn, setTopGrn] = useState<string | null>(null)
  const [warning, setWarning] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [queue, setQueue] = useState<PmOrderQueueRow | { status: null } | null>(null)
  const [syncing, setSyncing] = useState(false)
  const [syncNote, setSyncNote] = useState('')
  const [syncProgress, setSyncProgress] = useState(0)
  const [syncLog, setSyncLog] = useState<SyncLogLine[]>([])
  const [reloadToken, setReloadToken] = useState(0)

  useEffect(() => {
    legacyOrderService
      .listStores(true)
      .then((rows) => {
        setStores(rows)
        setLastSync(Object.fromEntries(rows.map((r) => [r.store_name, r.last_sync_time])))
        setStore((cur) => cur || rows[0]?.store_name || '')
      })
      .catch((err: unknown) => setError(errorMessage(err, 'Could not load your stores.')))
  }, [])

  // Trigger this module's own branch/agent -> central OrderNMC sync job
  // (legacyOrderService.startSync, the same one "Sync" in the legacy Order
  // Workspace starts -- NOT the unrelated platform sync.* pipeline, which
  // has its own separate store registry and never touches
  // OrderNMC.Stores.LastSyncTime), then poll the job until it finishes,
  // then reload the two grids -- "connect and load GRN and sales after
  // sync" (owner spec, 2026-11-24). Runs once on store load, and again
  // any time the PM hits Fetch Data.
  const runSync = useCallback(async () => {
    if (!store) return
    setSyncing(true)
    setSyncNote('Connecting to store…')
    setSyncProgress(5)
    setSyncLog([{ stamp: fmtLogStamp(new Date()), text: `Sync requested for ${store}` }])
    setError('')
    let loggedCount = 0
    try {
      const started = await legacyOrderService.startSync(store)
      const jobId = started.job_id
      if (!jobId) throw new Error('Sync did not return a job id.')
      const deadline = Date.now() + 10 * 60 * 1000
      // eslint-disable-next-line no-constant-condition
      while (true) {
        await new Promise((r) => setTimeout(r, 2000))
        const job = await legacyOrderService.getJob(jobId).catch(() => null)
        if (!job) continue
        const total = job.total_steps || 1
        setSyncProgress(Math.max(5, Math.min(99, Math.round(((job.step || 0) / total) * 100))))
        setSyncNote(job.message || 'Syncing…')
        const newLines = (job.log || []).slice(loggedCount)
        if (newLines.length) {
          loggedCount = job.log.length
          setSyncLog((log) => [...log, ...newLines.map((l) => ({ stamp: fmtLogStamp(new Date(l.at)), text: l.message }))])
        }
        if (job.status === 'completed' || job.status === 'failed' || Date.now() > deadline) {
          if (job.status === 'failed') throw new Error('Sync failed.')
          break
        }
      }
      setSyncProgress(100)
      setSyncNote('')
      setSyncLog((log) => [...log, { stamp: fmtLogStamp(new Date()), text: 'Sync complete. Order DB is up to date.' }])
      setLastSync((cur) => ({ ...cur, [store]: new Date().toISOString() }))
      setReloadToken((t) => t + 1)
    } catch (err) {
      setSyncNote('')
      setSyncLog((log) => [...log, { stamp: fmtLogStamp(new Date()), text: `Sync failed: ${errorMessage(err, 'unknown error')}` }])
      setError(errorMessage(err, 'Sync could not be started.'))
    } finally {
      setSyncing(false)
    }
  }, [store])

  useEffect(() => {
    if (store) runSync()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [store])

  const refresh = useCallback(() => {
    if (!store) return Promise.resolve()
    return legacyOrderService
      .pmOrderEntry(store)
      .then(setState)
      .catch((err: unknown) => setError(errorMessage(err, 'Could not load the order state.')))
  }, [store])

  const refreshQueue = useCallback(() => {
    if (!store) return Promise.resolve()
    return legacyOrderService
      .pmOrderEntryQueue(store)
      .then(setQueue)
      .catch(() => {})
  }, [store])

  useEffect(() => {
    setState(null)
    setQueue(null)
    refresh()
    refreshQueue()
  }, [refresh, refreshQueue])

  // Terminal states for the PM's simple waiting UI: a queued (automated) row
  // reaching DONE/FAILED, or a direct job reaching completed/failed. The PM
  // never sees which path it took -- see `simpleStatus` below.
  const queuePending = Boolean(queue && 'status' in queue && (queue.status === 'PENDING' || queue.status === 'RUNNING'))
  const running = state?.job?.status === 'running' || queuePending
  useEffect(() => {
    if (!running) return undefined
    const t = setInterval(() => {
      refresh()
      refreshQueue()
    }, POLL_MS)
    return () => clearInterval(t)
  }, [running, refresh, refreshQueue])

  const queueId = queue && 'queue_id' in queue ? queue.queue_id : null
  const queueStatus = queue?.status ?? null
  useEffect(() => {
    if (queueStatus === 'DONE') refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queueId, queueStatus])

  const submit = async (confirmed = false) => {
    if (!topBill || !topGrn) return
    setBusy(true)
    setError('')
    setWarning('')
    try {
      const result = await legacyOrderService.pmSubmitOrderEntry(store, {
        lastBill: topBill,
        lastGrn: topGrn,
        orderType: 'REGULAR', // order type is now a store-level admin setting, not a per-submit choice
        confirmed,
      })
      if ('queued' in result && result.queued) setQueue(result)
      await refresh()
    } catch (err) {
      const message = errorMessage(err, 'Could not start the order.')
      if (/pending supplier assignment|confirm order & process/i.test(message) && !confirmed) setWarning(message)
      else setError(message)
    } finally {
      setBusy(false)
    }
  }

  const order = state?.latest_order
  const canSubmit = Boolean(store && topBill && topGrn && !state?.blocked && !running && !busy && !syncing)

  // The PM sees only idle / "Submitted, please wait" / done -- never whether
  // this went through the automated queue or straight to a job, and never a
  // step-by-step log line (owner ruling: "pm user once check all purchase
  // entry finished ... submit its trigger sync ... their want two grid load
  // bill details and one submit button ... they dont know they trigger
  // order they think Admin only process the order"). Job-log detail is still
  // in the API response (service.py's _log/_update is untouched) for the
  // admin-facing Legacy Order console -- just never rendered here.
  const simpleStatus: 'idle' | 'submitted' | 'done' = running || busy ? 'submitted' : 'idle'

  return (
    <section className="pm-order-entry">
      <header className="poe-screen-head">
        <div>
          <h2>Order Entry</h2>
          <p>Review the recent GRNs and sale bills below against your paperwork, then submit.</p>
        </div>
        <div className="poe-tools">
          {stores.length > 1 && (
            <select aria-label="Store" value={store} onChange={(e) => setStore(e.target.value)}>
              {stores.map((s) => (
                <option key={s.store_name} value={s.store_name}>
                  {s.display_name || s.store_name}
                </option>
              ))}
            </select>
          )}
          <span className="poe-last-sync">
            <span className="poe-last-sync-label">Last sync</span>
            <span className="poe-last-sync-value">{fmtStamp(lastSync[store])}</span>
          </span>
          <button type="button" className="primary-button" disabled={syncing || !store} onClick={runSync}>
            {syncing ? 'Fetching…' : 'Fetch Data'}
          </button>
        </div>
      </header>

      {error && <div className="status-line error">{error}</div>}

      {syncing && (
        <section className="poe-card poe-sync-overlay">
          <div className="poe-sync-ring" role="status" aria-live="polite">
            <span className="poe-sync-ring-core" />
          </div>
          <div className="poe-sync-stage">{syncNote || 'Syncing…'}</div>
          <div className="poe-sync-bar">
            <div className="poe-sync-bar-fill" style={{ width: `${syncProgress}%` }} />
          </div>
          <div className="poe-sync-caption">Store → Nexora → Order DB</div>
          <div className="poe-sync-log">
            {syncLog.slice(-8).map((line, i) => (
              <div key={i} className="poe-sync-log-line">
                <span className="poe-muted">{line.stamp}</span> {line.text}
              </div>
            ))}
          </div>
        </section>
      )}

      <div className="poe-grid">
        <section className="poe-card">
          <header className="poe-card-head">
            <h3>Current order · {store || '—'}</h3>
          </header>
          {order?.order_id ? (
            <dl className="poe-meta">
              <div>
                <dt>Order</dt>
                <dd>
                  #{order.order_no ?? order.order_id} · {fmtStamp(state?.header?.order_datetime)}
                </dd>
              </div>
              <div>
                <dt>Status</dt>
                <dd className={order.status === ('FINALIZED' as OrderWorkflowStatus) ? 'poe-ok' : 'poe-warn'}>
                  {STATUS_LABEL[order.status] || order.status}
                </dd>
              </div>
              <div>
                <dt>Qty review pending</dt>
                <dd>{order.qty_pending}</dd>
              </div>
              <div>
                <dt>Unassigned</dt>
                <dd>{order.unassigned_lines}</dd>
              </div>
              <div>
                <dt>Last bill / GRN</dt>
                <dd>
                  {state?.header?.last_sale_bill_no || '—'} / {state?.header?.last_grn || '—'}
                </dd>
              </div>
            </dl>
          ) : (
            <p className="poe-muted">No order yet.</p>
          )}
          {state?.blocked && (
            <div className="status-line error">
              This order is from an earlier day and is not finalized. Review the pending products and Finalize it in
              Procurement before generating today&apos;s order.
            </div>
          )}
        </section>

        <section className="poe-card">
          <header className="poe-card-head">
            <h3>Submit</h3>
          </header>
          <div className="poe-form">
            <label>
              <span>Last bill</span>
              <div className="poe-readonly-field poe-readonly-field--value">{topBill || '—'}</div>
            </label>
            <label>
              <span>Last GRN</span>
              <div className="poe-readonly-field poe-readonly-field--value">{topGrn || '—'}</div>
            </label>
            <p className="poe-muted poe-auto-note">Picked up automatically from the top row of the grids below.</p>
          </div>
          {warning ? (
            <div className="status-line poe-warn">
              {warning}
              <button type="button" className="primary-button poe-inline-btn" disabled={busy} onClick={() => submit(true)}>
                Continue &amp; Process
              </button>
            </div>
          ) : (
            <button type="button" className="primary-button" disabled={!canSubmit} onClick={() => submit(false)}>
              {simpleStatus === 'submitted' ? 'Submitted, please wait…' : 'Submit'}
            </button>
          )}
          {simpleStatus === 'submitted' && (
            <div className="poe-muted">Your order is being processed. This card will update automatically when it&apos;s done.</div>
          )}
        </section>
      </div>

      {store && (
        <RecentVerificationGrids
          store={store}
          reloadToken={reloadToken}
          onTopRow={(bill, grn) => {
            setTopBill(bill)
            setTopGrn(grn)
          }}
        />
      )}
    </section>
  )
}
