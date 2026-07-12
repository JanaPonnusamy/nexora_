import { useCallback, useEffect, useMemo, useState } from 'react'
import { tenantService } from '../../services/tenantService'
import { storeService } from '../../services/storeService'
import { procurementService } from '../../services/procurementService'
import { syncService } from '../../services/syncService'
import { useActingUser } from '../../hooks/useActingUser'
import type { Tenant } from '../../types/tenant'
import type { Store } from '../../types/store'
import type { Cycle } from '../../types/procurement'
import { EmptyState } from '../../components/common/EmptyState'
import { num } from '../../components/stock/format'
import '../../components/procurement/purchase-manager.css'

type Banner = { kind: 'success' | 'danger'; text: string } | null

/** A single pipeline step's live state, shown as a chip in the store row. */
type StepState = 'idle' | 'running' | 'done' | 'failed' | 'skipped' | 'confirm'

/** Per-store run tracker. One store flows Sync -> Cycle -> Refresh; each phase's
 *  state drives the row's status chips. */
type RowRun = {
  storeId: string
  sync: StepState
  cycle: StepState
  refresh: StepState
  message?: string
  executionId?: string
  products?: number
}

const POLL_MS = 2500
const SYNC_TIMEOUT_MS = 240_000

const errMsg = (e: unknown) => (e instanceof Error ? e.message : 'Request failed')

/** COMPLETED -> ok, FAILED/CANCELLED -> fail, anything else -> keep polling. */
function terminal(status?: string | null): 'ok' | 'fail' | null {
  const s = (status ?? '').toUpperCase()
  if (s === 'COMPLETED') return 'ok'
  if (s === 'FAILED' || s === 'CANCELLED' || s === 'CANCELED') return 'fail'
  return null
}

/** Poll a sync execution until it reaches a terminal state or times out. */
function pollSync(execId: string, onTick?: (status: string) => void): Promise<'ok' | 'fail' | 'timeout'> {
  return new Promise((resolve) => {
    const start = Date.now()
    const tick = async () => {
      try {
        const sum = await syncService.executionSummary(execId)
        onTick?.(sum.status ?? '')
        const t = terminal(sum.status)
        if (t) return resolve(t)
      } catch {
        /* transient (agent mid-write / network blip) — keep polling */
      }
      if (Date.now() - start > SYNC_TIMEOUT_MS) return resolve('timeout')
      window.setTimeout(tick, POLL_MS)
    }
    window.setTimeout(tick, POLL_MS)
  })
}

/** Readable auto-name for a freshly opened cycle: "<store> · 12-Jul-2026". */
function autoCycleName(storeName: string): string {
  const d = new Date()
  const mon = d.toLocaleString('en-GB', { month: 'short' })
  return `${storeName} · ${String(d.getDate()).padStart(2, '0')}-${mon}-${d.getFullYear()}`
}

function StepChip({ label, state }: { label: string; state: StepState }) {
  const icon: Record<StepState, string> = {
    idle: 'bi-dash-circle',
    running: 'bi-arrow-repeat pm-spin',
    done: 'bi-check-circle-fill',
    failed: 'bi-x-circle-fill',
    skipped: 'bi-slash-circle',
    confirm: 'bi-exclamation-triangle-fill',
  }
  return (
    <span className={`pm-step pm-step--${state}`}>
      <i className={`bi ${icon[state]}`} /> {label}
    </span>
  )
}

/**
 * Cycle & Refresh Console (Procurement Admin) — one screen to run the whole
 * lifecycle across many stores at once. Per selected store the pipeline is:
 *
 *     Sync  ->  (New Cycle? close old + open fresh : keep active)  ->  Refresh + VPL
 *
 * A refresh only runs after its store's sync COMPLETES. Each store's live status
 * is shown in its own row. Reuses the existing lifecycle + sync endpoints; no
 * engine logic here.
 */
export default function CycleRefreshConsolePage() {
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [tenantId, setTenantId] = useState('')
  const [stores, setStores] = useState<Store[]>([])
  const [cyclesByStore, setCyclesByStore] = useState<Record<string, Cycle[]>>({})
  const actingUser = useActingUser()
  const [banner, setBanner] = useState<Banner>(null)

  // Selection + per-store "start a fresh cycle" toggle.
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [newCycle, setNewCycle] = useState<Set<string>>(new Set())

  // Shared refresh parameters (one set for the whole batch).
  const [rollingDays, setRollingDays] = useState('90')
  const [minDays, setMinDays] = useState('7')
  const [maxDays, setMaxDays] = useState('21')
  const [skipSync, setSkipSync] = useState(false)

  const [running, setRunning] = useState(false)
  const [runs, setRuns] = useState<Record<string, RowRun>>({})

  const say = useCallback((kind: 'success' | 'danger', text: string) => {
    setBanner({ kind, text })
    window.setTimeout(() => setBanner(null), 5000)
  }, [])
  const fail = useCallback((e: unknown) => say('danger', errMsg(e)), [say])

  useEffect(() => {
    tenantService.list().then((rows) => {
      const active = rows.filter((t) => t.is_active)
      setTenants(active)
      if (active.length) setTenantId((c) => c || active[0].tenant_id)
    }).catch(fail)
    storeService.list().then(setStores).catch(() => setStores([]))
  }, [fail])

  const tenantStores = useMemo(
    () => stores.filter((s) => s.tenant_id === tenantId && s.is_active),
    [stores, tenantId],
  )

  // Load the current cycles for every store in the tenant so the grid can show
  // each store's ACTIVE cycle (and reflect changes after a run).
  const reloadCycles = useCallback(() => {
    if (!tenantId) { setCyclesByStore({}); return }
    const list = stores.filter((s) => s.tenant_id === tenantId && s.is_active)
    Promise.all(
      list.map((s) =>
        procurementService.cycles(tenantId, s.store_id)
          .then((cs) => [s.store_id, cs] as const)
          .catch(() => [s.store_id, [] as Cycle[]] as const),
      ),
    ).then((pairs) => setCyclesByStore(Object.fromEntries(pairs)))
  }, [tenantId, stores])

  useEffect(() => { reloadCycles() }, [reloadCycles])

  // Keep selection valid when the tenant changes.
  useEffect(() => {
    const ids = new Set(tenantStores.map((s) => s.store_id))
    setSelected((cur) => new Set([...cur].filter((id) => ids.has(id))))
    setNewCycle((cur) => new Set([...cur].filter((id) => ids.has(id))))
    setRuns({})
  }, [tenantStores])

  const activeCycleOf = useCallback(
    (storeId: string): Cycle | null =>
      cyclesByStore[storeId]?.find((c) => (c.status ?? '').toUpperCase() === 'ACTIVE') ?? null,
    [cyclesByStore],
  )

  const patchRun = useCallback((storeId: string, patch: Partial<RowRun>) => {
    const base: RowRun = { storeId, sync: 'idle', cycle: 'idle', refresh: 'idle' }
    setRuns((prev) => ({ ...prev, [storeId]: { ...base, ...prev[storeId], ...patch } }))
  }, [])

  const toggle = (set: Set<string>, id: string) => {
    const next = new Set(set)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    return next
  }

  const allSelected = tenantStores.length > 0 && tenantStores.every((s) => selected.has(s.store_id))
  const allNewCycle = tenantStores.length > 0 && tenantStores.every((s) => newCycle.has(s.store_id))

  // --- The pipeline ---------------------------------------------------------

  /** Resolve the cycle (close+open a fresh one, open a first one, or keep the
   *  ACTIVE one) then generate a Refresh + VPL for it. Shared by the initial run
   *  and by the "Force close & continue" resume after a pending-confirm. */
  const runCycleAndRefresh = useCallback(
    async (store: Store, force: boolean, params: { rolling?: number; min: number; max: number }) => {
      // Resolve which cycle to refresh. Returns null (after patching the row's
      // status) when the store can't proceed — the pending-items confirm gate,
      // or no active cycle when "New Cycle" is off.
      const resolveCycle = async (): Promise<Cycle | null> => {
        const cycles = await procurementService.cycles(tenantId, store.store_id)
        const active = cycles.find((c) => (c.status ?? '').toUpperCase() === 'ACTIVE') ?? null
        if (newCycle.has(store.store_id)) {
          if (!active) {
            return procurementService.openCycle({
              tenant_id: tenantId,
              name: autoCycleName(store.store_name),
              store_id: store.store_id,
              created_by: actingUser,
            })
          }
          const res = await procurementService.closeCycle(tenantId, active.cycle_id, actingUser, force)
          if (res.status === 'pending_confirm') {
            patchRun(store.store_id, { cycle: 'confirm', message: res.message })
            return null
          }
          return res.new_cycle
        }
        if (!active) {
          patchRun(store.store_id, { cycle: 'failed', message: 'No active cycle — tick “New Cycle” to open one' })
          return null
        }
        return active
      }

      let target: Cycle
      try {
        patchRun(store.store_id, { cycle: 'running', message: 'Resolving cycle…' })
        const resolved = await resolveCycle()
        if (!resolved) return
        target = resolved
        patchRun(store.store_id, { cycle: 'done', message: `Cycle “${target.name}”` })
      } catch (e) {
        patchRun(store.store_id, { cycle: 'failed', message: errMsg(e) })
        return
      }

      try {
        patchRun(store.store_id, { refresh: 'running', message: 'Generating refresh + VPL…' })
        const r = await procurementService.generateRefresh(tenantId, target.cycle_id, {
          rolling_days: params.rolling,
          min_days: params.min,
          max_days: params.max,
          created_by: actingUser,
        })
        patchRun(store.store_id, {
          refresh: 'done',
          products: r.generated_product_count,
          message: `${num(r.generated_product_count)} products · ${num(r.working_item_count)} items`,
        })
      } catch (e) {
        patchRun(store.store_id, { refresh: 'failed', message: errMsg(e) })
      }
    },
    [tenantId, newCycle, actingUser, patchRun],
  )

  /** Full pipeline for one store: sync (unless skipped) then cycle + refresh. */
  const runStore = useCallback(
    async (store: Store, params: { rolling?: number; min: number; max: number }) => {
      patchRun(store.store_id, { sync: 'idle', cycle: 'idle', refresh: 'idle', message: '', products: undefined })

      if (skipSync) {
        patchRun(store.store_id, { sync: 'skipped', message: 'Sync skipped' })
      } else {
        try {
          patchRun(store.store_id, { sync: 'running', message: 'Creating sync task…' })
          const { task_id } = await syncService.createTask({
            tenant_id: tenantId, store_id: store.store_id, execution_type: 'FULL', sync_mode: 'FULL',
          })
          patchRun(store.store_id, { executionId: task_id, message: 'Waiting for store agent…' })
          const res = await pollSync(task_id, (s) =>
            patchRun(store.store_id, { message: `Sync ${s.toLowerCase()}…` }),
          )
          if (res !== 'ok') {
            patchRun(store.store_id, {
              sync: 'failed',
              message: res === 'timeout' ? 'Sync timed out — store agent did not finish' : 'Sync failed',
            })
            return
          }
          patchRun(store.store_id, { sync: 'done', message: 'Sync complete' })
        } catch (e) {
          patchRun(store.store_id, { sync: 'failed', message: errMsg(e) })
          return
        }
      }

      await runCycleAndRefresh(store, false, params)
    },
    [tenantId, skipSync, patchRun, runCycleAndRefresh],
  )

  const runBatch = async () => {
    const targets = tenantStores.filter((s) => selected.has(s.store_id))
    if (!targets.length) return say('danger', 'Select at least one store')
    const min = Number(minDays), max = Number(maxDays), roll = Number(rollingDays)
    if (Number.isNaN(min) || Number.isNaN(max) || min >= max) return say('danger', 'Min days must be less than Max days')
    const params = { rolling: Number.isNaN(roll) ? undefined : roll, min, max }

    setRunning(true)
    setRuns(Object.fromEntries(
      targets.map((s) => [s.store_id, { storeId: s.store_id, sync: 'idle', cycle: 'idle', refresh: 'idle' } as RowRun]),
    ))
    try {
      await Promise.all(targets.map((s) => runStore(s, params)))
    } finally {
      setRunning(false)
      reloadCycles()
    }
  }

  // Resume a store that stopped at the pending-items confirmation gate.
  const forceContinue = async (store: Store) => {
    const min = Number(minDays), max = Number(maxDays), roll = Number(rollingDays)
    const params = { rolling: Number.isNaN(roll) ? undefined : roll, min, max }
    setRunning(true)
    try {
      await runCycleAndRefresh(store, true, params)
    } finally {
      setRunning(false)
      reloadCycles()
    }
  }

  const anyConfirm = Object.values(runs).some((r) => r.cycle === 'confirm')

  return (
    <div className="pm-admin">
      <header className="pm-admin__head">
        <div className="pm-admin__title"><i className="bi bi-arrow-repeat" /> Cycle &amp; Refresh Console</div>
        <div className="pm-admin__ctx">
          <select className="sx-select" aria-label="Tenant" value={tenantId} onChange={(e) => setTenantId(e.target.value)} disabled={running}>
            {tenants.length === 0 && <option value="">Loading…</option>}
            {tenants.map((t) => <option key={t.tenant_id} value={t.tenant_id}>{t.tenant_name}</option>)}
          </select>
          <button className="pm-btn pm-btn--ghost" onClick={reloadCycles} disabled={running} title="Reload"><i className="bi bi-arrow-repeat" /></button>
        </div>
      </header>

      {banner && <div className={`pm-banner pm-banner--${banner.kind}`}>{banner.text}</div>}

      <section className="pm-admin__panel">
        <div className="pm-admin__panel-title">Run parameters</div>
        <div className="pm-admin__form">
          <label className="pm-admin__field"><span>Rolling days</span><input className="pm-input pm-input--sm" value={rollingDays} onChange={(e) => setRollingDays(e.target.value)} disabled={running} /></label>
          <label className="pm-admin__field"><span>Min days</span><input className="pm-input pm-input--sm" value={minDays} onChange={(e) => setMinDays(e.target.value)} disabled={running} /></label>
          <label className="pm-admin__field"><span>Max days</span><input className="pm-input pm-input--sm" value={maxDays} onChange={(e) => setMaxDays(e.target.value)} disabled={running} /></label>
          <label className="pm-console__opt" title="Skip the sync step and run cycle + refresh straight away">
            <input type="checkbox" checked={skipSync} onChange={(e) => setSkipSync(e.target.checked)} disabled={running} />
            <span>Skip sync</span>
          </label>
          <button className="pm-btn pm-btn--primary" disabled={running || selected.size === 0} onClick={runBatch}>
            <i className="bi bi-play-fill" /> {running ? 'Running…' : `Run ${selected.size || ''} store${selected.size === 1 ? '' : 's'}`.trim()}
          </button>
        </div>
        <div className="pm-console__legend">
          Each selected store runs <b>Sync</b> → <b>Cycle</b> → <b>Refresh + VPL</b>. Refresh runs only after sync completes.
          Tick <b>New Cycle</b> to close the current cycle and open a fresh one; leave it clear to keep the active cycle.
        </div>
      </section>

      {tenantStores.length === 0 ? (
        <EmptyState icon="bi-shop" title="No stores" description="This tenant has no active stores." />
      ) : (
        <table className="pm-grid pm-admin__table">
          <thead>
            <tr>
              <th className="pm-console__ck">
                <input
                  type="checkbox"
                  aria-label="Select all"
                  checked={allSelected}
                  disabled={running}
                  onChange={() => setSelected(allSelected ? new Set() : new Set(tenantStores.map((s) => s.store_id)))}
                />
              </th>
              <th>Store</th>
              <th>Active Cycle</th>
              <th className="pm-console__ck">
                <span className="pm-console__nchdr" title="Toggle New Cycle for all">
                  <input
                    type="checkbox"
                    aria-label="New cycle for all"
                    checked={allNewCycle}
                    disabled={running}
                    onChange={() => setNewCycle(allNewCycle ? new Set() : new Set(tenantStores.map((s) => s.store_id)))}
                  />
                  <span>New</span>
                </span>
              </th>
              <th>Status</th>
              <th className="pm-grid__act">Result</th>
            </tr>
          </thead>
          <tbody>
            {tenantStores.map((s) => {
              const run = runs[s.store_id]
              const active = activeCycleOf(s.store_id)
              return (
                <tr key={s.store_id}>
                  <td className="pm-console__ck">
                    <input
                      type="checkbox"
                      aria-label={`Select ${s.store_name}`}
                      checked={selected.has(s.store_id)}
                      disabled={running}
                      onChange={() => setSelected((cur) => toggle(cur, s.store_id))}
                    />
                  </td>
                  <td>
                    <div className="pm-prod__name">{s.store_name}</div>
                    <div className="pm-prod__meta">{s.store_code}</div>
                  </td>
                  <td>
                    {active
                      ? <span className="pm-badge pm-badge--ok">{active.name}</span>
                      : <span className="pm-badge pm-badge--muted">none</span>}
                  </td>
                  <td className="pm-console__ck">
                    <input
                      type="checkbox"
                      aria-label={`New cycle for ${s.store_name}`}
                      checked={newCycle.has(s.store_id)}
                      disabled={running}
                      onChange={() => setNewCycle((cur) => toggle(cur, s.store_id))}
                    />
                  </td>
                  <td>
                    {run ? (
                      <div className="pm-console__status">
                        <div className="pm-steps">
                          <StepChip label="Sync" state={run.sync} />
                          <StepChip label="Cycle" state={run.cycle} />
                          <StepChip label="Refresh" state={run.refresh} />
                        </div>
                        {run.message && <div className="pm-console__msg">{run.message}</div>}
                        {run.cycle === 'confirm' && (
                          <button className="pm-btn pm-btn--ghost pm-btn--sm" disabled={running} onClick={() => forceContinue(s)}>
                            Force close &amp; continue
                          </button>
                        )}
                      </div>
                    ) : (
                      <span className="sx-dim">—</span>
                    )}
                  </td>
                  <td className="pm-grid__act sx-num">
                    {run?.refresh === 'done' ? num(run.products ?? 0) : '—'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}

      {anyConfirm && (
        <div className="pm-console__note">
          <i className="bi bi-exclamation-triangle" /> One or more stores have pending items. “Force close &amp; continue”
          clears them (they are <b>not</b> carried forward) and opens a fresh cycle.
        </div>
      )}
    </div>
  )
}
