import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { tenantService } from '../../services/tenantService'
import { storeService } from '../../services/storeService'
import { procurementService } from '../../services/procurementService'
import { syncService } from '../../services/syncService'
import { intelligenceService } from '../../services/intelligenceService'
import { useActingUser } from '../../hooks/useActingUser'
import type { Tenant } from '../../types/tenant'
import type { Store } from '../../types/store'
import type { Cycle } from '../../types/procurement'
import { EmptyState } from '../../components/common/EmptyState'
import { num } from '../../components/stock/format'
import '../../components/procurement/purchase-manager.css'

type Banner = { kind: 'success' | 'danger'; text: string } | null

type StageKey = 'sync' | 'cycle' | 'refresh'
type StageStatus = 'waiting' | 'running' | 'completed' | 'failed' | 'skipped'
/** `confirm` = parked at the existing pending-items gate, awaiting the user. */
type StoreStatus = 'waiting' | 'running' | 'completed' | 'failed' | 'confirm'

type Stage = { status: StageStatus; startedAt?: number; endedAt?: number }
type LogEntry = { at: number; text: string }

/** Exactly what the existing refresh endpoint reports back. No supplier /
 *  deferred / skipped counts exist at generation time — see RefreshRunResult. */
type RefreshResult = {
  products: number
  included: number
  excluded: number
  workingItems: number
  carriedForward: number
}

type StoreRun = {
  storeId: string
  status: StoreStatus
  stages: Record<StageKey, Stage>
  log: LogEntry[]
  executionId?: string
  /** Cycle resolved by the Cycle stage. A refresh-stage retry reuses this so it
   *  can NEVER close/open a second cycle. */
  cycleId?: string
  cycleName?: string
  result?: RefreshResult
  message?: string
  startedAt?: number
  endedAt?: number
}

type Params = { rolling?: number; min: number; max: number }
/** keep = refresh the active cycle · closeRefresh = lock the current refresh &
 *  start a fresh one in the SAME cycle · new = close the cycle & open a fresh one. */
type CycleAction = 'keep' | 'closeRefresh' | 'new'
type RefreshInfo = { count: number; latestName: string | null; latestNo: number | null; latestAt: string | null }

const POLL_MS = 2500
const SYNC_TIMEOUT_MS = 240_000
const STAGES: StageKey[] = ['sync', 'cycle', 'refresh']
const STAGE_LABEL: Record<StageKey, string> = { sync: 'Sync', cycle: 'Cycle', refresh: 'Refresh' }

const errMsg = (e: unknown) => (e instanceof Error ? e.message : 'Request failed')

const clock = (t: number) =>
  new Date(t).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })

/** 18s · 1m 12s — compact, so it fits inside a stage chip. */
function dur(ms?: number): string {
  if (ms == null || ms < 0) return '—'
  const s = Math.round(ms / 1000)
  if (s < 60) return `${s}s`
  return `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, '0')}s`
}

const stageMs = (s: Stage, now: number) =>
  s.startedAt == null ? undefined : (s.endedAt ?? now) - s.startedAt
const runMs = (r: StoreRun, now: number) =>
  r.startedAt == null ? undefined : (r.endedAt ?? now) - r.startedAt

function terminal(status?: string | null): 'ok' | 'fail' | null {
  const s = (status ?? '').toUpperCase()
  if (s === 'COMPLETED') return 'ok'
  if (s === 'FAILED' || s === 'CANCELLED' || s === 'CANCELED') return 'fail'
  return null
}

type PollOutcome = 'ok' | 'fail' | 'timeout' | 'cancelled'

/** Poll one sync execution. Resolves — and therefore stops scheduling further
 *  requests — the instant it completes, fails, times out or is cancelled. */
function pollSync(
  execId: string,
  onProgress: (pct: number | null) => void,
  cancelled: () => boolean,
): Promise<PollOutcome> {
  return new Promise((resolve) => {
    const start = Date.now()
    const tick = async () => {
      if (cancelled()) return resolve('cancelled')
      try {
        const sum = await syncService.executionSummary(execId)
        if (cancelled()) return resolve('cancelled')
        const total = sum.total_tables ?? 0
        const done = sum.completed_tables ?? 0
        onProgress(total > 0 ? Math.min(100, Math.round((done / total) * 100)) : null)
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

// Mirrors the server-authoritative convention (orchestration_service.cycle_name).
// The server overrides this on open, but keeping it aligned avoids a flash of a
// different name in any optimistic UI.
const autoCycleName = (storeName: string) => {
  const d = new Date()
  const ymd = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  return `${storeName} - ${ymd} - Cycle`
}

/** Compact relative day label for a refresh timestamp — "Today 10:30",
 *  "Yesterday", or "12 Jul". */
function refreshWhen(iso?: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const today = new Date(); today.setHours(0, 0, 0, 0)
  const that = new Date(d); that.setHours(0, 0, 0, 0)
  const days = Math.round((today.getTime() - that.getTime()) / 86_400_000)
  const time = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })
  if (days === 0) return `Today ${time}`
  if (days === 1) return 'Yesterday'
  return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' })
}

// --- Pure run reducers ------------------------------------------------------

const blankRun = (storeId: string): StoreRun => ({
  storeId,
  status: 'waiting',
  stages: { sync: { status: 'waiting' }, cycle: { status: 'waiting' }, refresh: { status: 'waiting' } },
  log: [],
})

const addLog = (r: StoreRun, text: string): StoreRun => ({ ...r, log: [...r.log, { at: Date.now(), text }] })

const beginStage = (r: StoreRun, k: StageKey, text: string): StoreRun =>
  addLog({
    ...r,
    status: 'running',
    startedAt: r.startedAt ?? Date.now(),
    stages: { ...r.stages, [k]: { status: 'running', startedAt: Date.now() } },
  }, text)

const doneStage = (r: StoreRun, k: StageKey, text: string): StoreRun =>
  addLog({
    ...r,
    stages: { ...r.stages, [k]: { ...r.stages[k], status: 'completed', endedAt: Date.now() } },
  }, text)

const skipStage = (r: StoreRun, k: StageKey, text: string): StoreRun =>
  addLog({ ...r, stages: { ...r.stages, [k]: { status: 'skipped' } } }, text)

/** Fail one stage — and the store. Other stores are unaffected. */
const failStage = (r: StoreRun, k: StageKey, msg: string): StoreRun =>
  addLog({
    ...r,
    status: 'failed',
    message: msg,
    endedAt: Date.now(),
    stages: { ...r.stages, [k]: { ...r.stages[k], status: 'failed', endedAt: Date.now() } },
  }, `${STAGE_LABEL[k]} failed — ${msg}`)

function StageChip({ label, stage, now }: { label: string; stage: Stage; now: number }) {
  const icon: Record<StageStatus, string> = {
    waiting: 'bi-clock',
    running: 'bi-arrow-repeat pm-spin',
    completed: 'bi-check-circle-fill',
    failed: 'bi-x-circle-fill',
    skipped: 'bi-slash-circle',
  }
  const ms = stageMs(stage, now)
  return (
    <span className={`pm-step pm-step--${stage.status}`}>
      <i className={`bi ${icon[stage.status]}`} /> {label}
      {ms != null && <b className="pm-step__t">{dur(ms)}</b>}
    </span>
  )
}

/**
 * Cycle & Refresh Console (Procurement Admin) — run the whole procurement
 * lifecycle across many stores from one screen. Each selected store is an
 * INDEPENDENT pipeline:
 *
 *     Waiting -> Sync -> Cycle -> Refresh (Decision Engine + VPL) -> Completed
 *
 * A store that fails never stops the others; it can be retried on its own, from
 * the stage that failed. Pure orchestration over the existing endpoints — no
 * engine, cycle or refresh business logic lives here.
 */
export default function CycleRefreshConsolePage() {
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [tenantId, setTenantId] = useState('')
  const [stores, setStores] = useState<Store[]>([])
  const [cyclesByStore, setCyclesByStore] = useState<Record<string, Cycle[]>>({})
  /** Last refresh's product count per store — powers the pre-run estimate. */
  const [lastProducts, setLastProducts] = useState<Record<string, number | null>>({})
  /** Latest-refresh visibility per store — refresh count + the latest refresh's
   *  name / number / timestamp, so a buyer sees the active refresh at a glance. */
  const [refreshInfo, setRefreshInfo] = useState<Record<string, RefreshInfo>>({})
  const actingUser = useActingUser()
  const [banner, setBanner] = useState<Banner>(null)

  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [cycleAction, setCycleAction] = useState<Record<string, CycleAction>>({})
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const [rollingDays, setRollingDays] = useState('90')
  const [minDays, setMinDays] = useState('7')
  const [maxDays, setMaxDays] = useState('21')
  const [useExistingData, setUseExistingData] = useState(false)

  /** The store the network purchase quantity is calculated FOR once every
   *  selected store's VPL is built. Empty = do not consolidate. */
  const [warehouseId, setWarehouseId] = useState('')
  const [consolidating, setConsolidating] = useState(false)
  /** Stores whose VPL actually generated in this batch (runPipeline records a
   *  failure on the store instead of throwing, so a settled promise proves nothing). */
  const refreshed = useRef<Set<string>>(new Set())

  const [running, setRunning] = useState(false)
  const [runs, setRuns] = useState<Record<string, StoreRun>>({})
  const [batch, setBatch] = useState<{ start: number; end: number | null } | null>(null)

  // Ticks only while work is in flight, so live durations count up without
  // re-rendering an idle page.
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    if (!running) return
    const t = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(t)
  }, [running])

  // Stops every in-flight poll the moment the page unmounts.
  const cancelled = useRef(false)
  useEffect(() => () => { cancelled.current = true }, [])

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

  /** One parallel round: each store's cycles + its last refresh size. */
  const reloadContext = useCallback(() => {
    if (!tenantId) { setCyclesByStore({}); setLastProducts({}); setRefreshInfo({}); return }
    const list = stores.filter((s) => s.tenant_id === tenantId && s.is_active)
    Promise.all(list.map(async (s) => {
      const [cycles, refreshes] = await Promise.all([
        procurementService.cycles(tenantId, s.store_id).catch(() => [] as Cycle[]),
        procurementService.refreshes(tenantId, s.store_id).catch(() => []),
      ])
      // Latest refresh IN THE ACTIVE CYCLE — the one a buyer is actually working;
      // fall back to the store-wide latest when no cycle is active.
      const active = cycles.find((c) => (c.status ?? '').toUpperCase() === 'ACTIVE')
      const scoped = active ? refreshes.filter((r) => r.cycle_id === active.cycle_id) : refreshes
      const latest = [...scoped].sort((a, b) => (b.refresh_no ?? 0) - (a.refresh_no ?? 0))[0]
      const info: RefreshInfo = {
        count: scoped.length,
        latestName: latest?.snapshot_name ?? null,
        latestNo: latest?.refresh_no ?? null,
        latestAt: latest?.created_at ?? null,
      }
      return [s.store_id, cycles, latest?.generated_product_count ?? null, info] as const
    })).then((rows) => {
      setCyclesByStore(Object.fromEntries(rows.map((r) => [r[0], r[1]])))
      setLastProducts(Object.fromEntries(rows.map((r) => [r[0], r[2]])))
      setRefreshInfo(Object.fromEntries(rows.map((r) => [r[0], r[3]])))
    }).catch(() => { /* keep last good context */ })
  }, [tenantId, stores])

  useEffect(() => { reloadContext() }, [reloadContext])

  useEffect(() => {
    const ids = new Set(tenantStores.map((s) => s.store_id))
    setSelected((cur) => new Set([...cur].filter((id) => ids.has(id))))
    setRuns({})
    setBatch(null)
  }, [tenantStores])

  const activeCycleOf = useCallback(
    (storeId: string) => cyclesByStore[storeId]?.find((c) => (c.status ?? '').toUpperCase() === 'ACTIVE') ?? null,
    [cyclesByStore],
  )

  const update = useCallback((id: string, fn: (r: StoreRun) => StoreRun) => {
    setRuns((prev) => ({ ...prev, [id]: fn(prev[id] ?? blankRun(id)) }))
  }, [])

  const parseParams = (): Params | null => {
    const min = Number(minDays), max = Number(maxDays), roll = Number(rollingDays)
    if (Number.isNaN(min) || Number.isNaN(max) || min >= max) {
      say('danger', 'Min days must be less than Max days')
      return null
    }
    return { rolling: Number.isNaN(roll) ? undefined : roll, min, max }
  }

  // --- Pipeline -------------------------------------------------------------

  /** Run one store from `from` onward. Never throws: a failure is recorded on
   *  that store's run and the other stores keep going. */
  const runPipeline = useCallback(async (
    store: Store,
    from: StageKey,
    params: Params,
    opts: { force?: boolean; cycleId?: string } = {},
  ) => {
    const id = store.store_id
    const startIdx = STAGES.indexOf(from)

    // Reset the stages about to be (re)run, so a retry shows a clean slate.
    update(id, (r) => {
      const stages = { ...r.stages }
      STAGES.forEach((k, i) => { if (i >= startIdx) stages[k] = { status: 'waiting' } })
      return {
        ...r,
        status: 'running',
        message: undefined,
        endedAt: undefined,
        startedAt: from === 'sync' ? Date.now() : r.startedAt ?? Date.now(),
        stages,
      }
    })

    // 1) Sync — gates everything after it.
    if (startIdx <= STAGES.indexOf('sync')) {
      if (useExistingData) {
        update(id, (r) => skipStage(r, 'sync', 'Using existing store data — sync skipped'))
      } else {
        update(id, (r) => beginStage(r, 'sync', 'Sync started'))
        try {
          const { task_id } = await syncService.createTask({
            tenant_id: tenantId, store_id: id, execution_type: 'FULL', sync_mode: 'FULL',
          })
          update(id, (r) => addLog({ ...r, executionId: task_id }, 'Waiting for store agent…'))

          let lastPct = -1
          const outcome = await pollSync(task_id, (pct) => {
            if (pct != null && pct !== lastPct) {
              lastPct = pct
              update(id, (r) => addLog(r, `Sync ${pct}%`))
            }
          }, () => cancelled.current)

          if (outcome === 'cancelled') return
          if (outcome !== 'ok') {
            update(id, (r) => failStage(r, 'sync',
              outcome === 'timeout' ? 'Store agent did not finish in time' : 'Sync failed'))
            return
          }
          update(id, (r) => doneStage(r, 'sync', 'Sync complete'))
        } catch (e) {
          update(id, (r) => failStage(r, 'sync', errMsg(e)))
          return
        }
      }
    }

    // 2) Cycle — keep the ACTIVE one, or close it and open a fresh one.
    let cycleId = opts.cycleId
    // The refresh to lock before generating the next one (Close Refresh action).
    let refreshToClose: string | undefined
    const action: CycleAction = cycleAction[id] ?? 'keep'
    if (startIdx <= STAGES.indexOf('cycle')) {
      update(id, (r) => beginStage(r, 'cycle', 'Resolving cycle…'))
      try {
        const wantNew = action === 'new'
        const cycles = await procurementService.cycles(tenantId, id)
        const active = cycles.find((c) => (c.status ?? '').toUpperCase() === 'ACTIVE') ?? null

        let target: Cycle
        if (!wantNew) {
          if (!active) {
            update(id, (r) => failStage(r, 'cycle', 'No active cycle — set Cycle Action to “Create New Cycle”'))
            return
          }
          target = active
          // Close Refresh: lock the cycle's current refresh; the refresh stage
          // then generates Refresh N+1 in this same open cycle.
          if (action === 'closeRefresh') refreshToClose = active.active_refresh_id ?? undefined
        } else if (!active) {
          update(id, (r) => addLog(r, 'No cycle yet — opening the first one'))
          target = await procurementService.openCycle({
            tenant_id: tenantId,
            name: autoCycleName(store.store_name),
            store_id: id,
            created_by: actingUser,
          })
          update(id, (r) => addLog(r, `Opened cycle “${target.name}”`))
        } else {
          update(id, (r) => addLog(r, `Closing cycle “${active.name}”`))
          const res = await procurementService.closeCycle(tenantId, active.cycle_id, actingUser, opts.force ?? false)
          if (res.status === 'pending_confirm') {
            // Park at the existing gate — do not clear pending behind the user's back.
            update(id, (r) => addLog({
              ...r,
              status: 'confirm',
              message: res.message,
              stages: { ...r.stages, cycle: { ...r.stages.cycle, status: 'waiting', endedAt: Date.now() } },
            }, 'Pending items remain — awaiting confirmation'))
            return
          }
          target = res.new_cycle
          update(id, (r) => addLog(r, `Opened cycle “${target.name}”`))
        }

        cycleId = target.cycle_id
        update(id, (r) => doneStage({ ...r, cycleId: target.cycle_id, cycleName: target.name },
          'cycle', `Cycle ready — “${target.name}”`))
      } catch (e) {
        update(id, (r) => failStage(r, 'cycle', errMsg(e)))
        return
      }
    }

    // 3) Refresh — Decision Engine + VPL + working items (one existing call).
    if (!cycleId) {
      update(id, (r) => failStage(r, 'refresh', 'No cycle resolved'))
      return
    }
    update(id, (r) => beginStage(r, 'refresh', 'Running Decision Engine, building VPL…'))
    try {
      if (refreshToClose) {
        await procurementService.closeRefresh(tenantId, refreshToClose, actingUser)
        update(id, (r) => addLog(r, 'Closed the current refresh (locked read-only)'))
      }
      const res = await procurementService.generateRefresh(tenantId, cycleId, {
        rolling_days: params.rolling, min_days: params.min, max_days: params.max, created_by: actingUser,
      })
      const result: RefreshResult = {
        products: res.generated_product_count ?? 0,
        included: res.included_count ?? 0,
        excluded: res.excluded_count ?? 0,
        workingItems: res.working_item_count ?? 0,
        carriedForward: res.carried_forward_count ?? 0,
      }
      refreshed.current.add(id)
      update(id, (r) => {
        const next = doneStage({ ...r, result }, 'refresh',
          `Refresh completed — ${num(result.products)} products, ${num(result.workingItems)} working items`)
        return { ...next, status: 'completed', endedAt: Date.now() }
      })
    } catch (e) {
      update(id, (r) => failStage(r, 'refresh', errMsg(e)))
    }
  }, [tenantId, actingUser, cycleAction, useExistingData, update])

  /** Consolidate every refreshed store's VPL into the network Product
   *  Intelligence grid. Runs once, after the whole batch, so the intelligence can
   *  never be stale relative to the refresh that produced it. A failure here is
   *  reported but never fails the refresh run — the VPLs are already persisted. */
  const consolidate = useCallback(async (storeIds: string[]) => {
    if (!warehouseId || !storeIds.length) return
    setConsolidating(true)
    try {
      const res = await intelligenceService.build(tenantId, warehouseId, storeIds, actingUser)
      say('success',
        `Product Intelligence rebuilt — ${num(res.product_count)} canonical products from ` +
        `${res.store_count} store VPLs · warehouse buys ${num(res.total_purchase_qty)}`)
    } catch (e) {
      say('danger', `Refresh succeeded, but consolidation failed: ${errMsg(e)}`)
    } finally {
      setConsolidating(false)
    }
  }, [tenantId, warehouseId, actingUser, say])

  const runBatch = async () => {
    const targets = tenantStores.filter((s) => selected.has(s.store_id))
    if (!targets.length) return say('danger', 'Select at least one store')
    const params = parseParams()
    if (!params) return

    cancelled.current = false
    setRuns(Object.fromEntries(targets.map((s) => [s.store_id, blankRun(s.store_id)])))
    setBatch({ start: Date.now(), end: null })
    setRunning(true)
    try {
      // Parallel, and isolated: one store's failure cannot reject the batch.
      refreshed.current.clear()
      await Promise.allSettled(targets.map((s) => runPipeline(s, 'sync', params)))
      // Consolidate only the stores whose VPL actually generated (runPipeline
      // records a failure on the store rather than throwing, so a settled promise
      // does NOT mean the store succeeded).
      await consolidate([...refreshed.current])
    } finally {
      setRunning(false)
      setBatch((b) => (b ? { ...b, end: Date.now() } : b))
      reloadContext()
    }
  }

  /** Retry ONE store, resuming at the stage that failed. A refresh-stage retry
   *  reuses the cycle already resolved, so it cannot close a second cycle. */
  const retry = async (store: Store) => {
    const run = runs[store.store_id]
    if (!run) return
    const params = parseParams()
    if (!params) return
    const from: StageKey =
      run.stages.sync.status === 'failed' ? 'sync'
        : run.stages.cycle.status === 'failed' ? 'cycle'
          : 'refresh'

    cancelled.current = false
    setRunning(true)
    try {
      await runPipeline(store, from, params, { cycleId: run.cycleId })
    } finally {
      setRunning(false)
      reloadContext()
    }
  }

  /** Confirmed close-with-pending: re-run the cycle stage with force. */
  const forceContinue = async (store: Store) => {
    const params = parseParams()
    if (!params) return
    cancelled.current = false
    setRunning(true)
    try {
      await runPipeline(store, 'cycle', params, { force: true })
    } finally {
      setRunning(false)
      reloadContext()
    }
  }

  // --- Derived --------------------------------------------------------------

  const allSelected = tenantStores.length > 0 && tenantStores.every((s) => selected.has(s.store_id))

  /** Pre-run estimate, from each store's last refresh (when it has one). */
  const workload = useMemo(() => {
    const ids = [...selected]
    const known = ids.map((id) => lastProducts[id]).filter((v): v is number => typeof v === 'number')
    return {
      stores: ids.length,
      products: known.reduce((a, b) => a + b, 0),
      withData: known.length,
      unknown: ids.length - known.length,
    }
  }, [selected, lastProducts])

  const summary = useMemo(() => {
    const list = Object.values(runs)
    if (!list.length) return null
    const done = list.filter((r) => r.status === 'completed')
    return {
      selected: list.length,
      completed: done.length,
      failed: list.filter((r) => r.status === 'failed').length,
      products: done.reduce((a, r) => a + (r.result?.products ?? 0), 0),
      workingItems: done.reduce((a, r) => a + (r.result?.workingItems ?? 0), 0),
      carried: done.reduce((a, r) => a + (r.result?.carriedForward ?? 0), 0),
      duration: batch?.end != null ? batch.end - batch.start : undefined,
    }
  }, [runs, batch])

  const showSummary = summary != null && !running && batch?.end != null

  return (
    <div className="pm-admin pm-console">
      <header className="pm-admin__head">
        <div className="pm-admin__title"><i className="bi bi-arrow-repeat" /> Cycle &amp; Refresh Console</div>
        <div className="pm-admin__ctx">
          <select className="sx-select" aria-label="Tenant" value={tenantId} onChange={(e) => setTenantId(e.target.value)} disabled={running}>
            {tenants.length === 0 && <option value="">Loading…</option>}
            {tenants.map((t) => <option key={t.tenant_id} value={t.tenant_id}>{t.tenant_name}</option>)}
          </select>
          <button className="pm-btn pm-btn--ghost" onClick={reloadContext} disabled={running} title="Reload"><i className="bi bi-arrow-clockwise" /></button>
        </div>
      </header>

      {banner && <div className={`pm-banner pm-banner--${banner.kind}`}>{banner.text}</div>}

      <section className="pm-admin__panel pm-console__bar">
        <div className="pm-admin__form">
          <label className="pm-admin__field"><span>Rolling days</span><input className="pm-input pm-input--sm" value={rollingDays} onChange={(e) => setRollingDays(e.target.value)} disabled={running} /></label>
          <label className="pm-admin__field"><span>Min days</span><input className="pm-input pm-input--sm" value={minDays} onChange={(e) => setMinDays(e.target.value)} disabled={running} /></label>
          <label className="pm-admin__field"><span>Max days</span><input className="pm-input pm-input--sm" value={maxDays} onChange={(e) => setMaxDays(e.target.value)} disabled={running} /></label>
          <label className="pm-console__opt" title="Skip the sync stage and refresh from the data already synced">
            <input type="checkbox" checked={useExistingData} onChange={(e) => setUseExistingData(e.target.checked)} disabled={running} />
            <span>Use Existing Store Data</span>
          </label>
          <label
            className="pm-admin__field"
            title="Every store's VPL is merged into one network grid, and the purchase quantity is calculated FOR this store"
          >
            <span>Buying warehouse</span>
            <select
              className="sx-select sx-select--sm"
              value={warehouseId}
              onChange={(e) => setWarehouseId(e.target.value)}
              disabled={running}
            >
              <option value="">Skip consolidation</option>
              {tenantStores.map((s) => (
                <option key={s.store_id} value={s.store_id}>{s.store_name}</option>
              ))}
            </select>
          </label>
          <button className="pm-btn pm-btn--primary pm-console__run" disabled={running || selected.size === 0} onClick={runBatch}>
            <i className="bi bi-play-fill" /> {consolidating ? 'Consolidating…' : running ? 'Running…' : `Run ${selected.size || ''} store${selected.size === 1 ? '' : 's'}`.replace('  ', ' ')}
          </button>
        </div>

        <div className="pm-console__work">
          <span><b>{workload.stores}</b> selected</span>
          {workload.withData > 0 && (
            <span title="Sum of each store's last refresh — an estimate, not a promise">
              ≈ <b>{num(workload.products)}</b> products
            </span>
          )}
          {workload.unknown > 0 && <span className="sx-dim">{workload.unknown} with no prior refresh</span>}
          <span className="sx-dim pm-console__flow">Sync → Cycle → Refresh (Decision Engine + VPL)</span>
        </div>
      </section>

      {showSummary && (
        <section className={`pm-console__summary ${summary.failed ? 'pm-console__summary--warn' : ''}`}>
          <div className="pm-console__sumitem"><b>{summary.completed}</b><span>of {summary.selected} completed</span></div>
          {summary.failed > 0 && <div className="pm-console__sumitem pm-console__sumitem--bad"><b>{summary.failed}</b><span>failed</span></div>}
          <div className="pm-console__sumitem"><b>{num(summary.products)}</b><span>products</span></div>
          <div className="pm-console__sumitem"><b>{num(summary.workingItems)}</b><span>working items</span></div>
          <div className="pm-console__sumitem"><b>{num(summary.carried)}</b><span>carried forward</span></div>
          <div className="pm-console__sumitem"><b>{dur(summary.duration)}</b><span>total</span></div>
        </section>
      )}

      {tenantStores.length === 0 ? (
        <EmptyState icon="bi-shop" title="No stores" description="This tenant has no active stores." />
      ) : (
        <table className="pm-grid pm-admin__table pm-console__grid">
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
              <th className="pm-console__cyclecol">Current Cycle</th>
              <th className="pm-console__refreshcol">Latest Refresh</th>
              <th className="pm-console__actioncol">
                Cycle Action
                <button
                  type="button"
                  className="pm-console__setall"
                  disabled={running}
                  title="Set every store to Create New Cycle"
                  onClick={() => setCycleAction(Object.fromEntries(tenantStores.map((s) => [s.store_id, 'new' as CycleAction])))}
                >
                  all new
                </button>
                <button
                  type="button"
                  className="pm-console__setall"
                  disabled={running}
                  title="Set every store to Keep Active"
                  onClick={() => setCycleAction({})}
                >
                  all keep
                </button>
              </th>
              <th>Pipeline</th>
              <th className="pm-console__rescol">Result</th>
              <th className="pm-console__timecol">Total</th>
              <th className="pm-console__actcol" />
            </tr>
          </thead>
          <tbody>
            {tenantStores.map((s) => {
              const id = s.store_id
              const run = runs[id]
              const active = activeCycleOf(id)
              const info = refreshInfo[id]
              const action = cycleAction[id] ?? 'keep'
              const isOpen = expanded.has(id)
              return [
                <tr key={id} className={run ? `pm-console__row pm-console__row--${run.status}` : 'pm-console__row'}>
                  <td className="pm-console__ck">
                    <input
                      type="checkbox"
                      aria-label={`Select ${s.store_name}`}
                      checked={selected.has(id)}
                      disabled={running}
                      onChange={() => setSelected((cur) => {
                        const next = new Set(cur)
                        if (next.has(id)) next.delete(id)
                        else next.add(id)
                        return next
                      })}
                    />
                  </td>
                  <td>
                    <div className="pm-prod__name">{s.store_name}</div>
                    <div className="pm-prod__meta">{s.store_code}</div>
                  </td>
                  <td className="pm-console__cyclecol">
                    {active ? (
                      <>
                        <div className="pm-console__cyclename" title={active.name}>{active.name}</div>
                        <span className="pm-badge pm-badge--active">Active</span>
                      </>
                    ) : (
                      <span className="sx-dim">No open cycle</span>
                    )}
                  </td>
                  <td className="pm-console__refreshcol">
                    {info?.latestName ? (
                      <>
                        <div className="pm-console__refreshname">
                          {info.latestNo != null ? `Refresh ${info.latestNo}` : info.latestName}
                          <span className="pm-console__refreshcount">{info.count} total</span>
                        </div>
                        <div className="pm-prod__meta">{refreshWhen(info.latestAt)}</div>
                      </>
                    ) : (
                      <span className="sx-dim">No refresh yet</span>
                    )}
                  </td>
                  <td className="pm-console__actioncol">
                    <select
                      className="sx-select sx-select--sm"
                      aria-label={`Cycle action for ${s.store_name}`}
                      value={action}
                      disabled={running}
                      onChange={(e) => setCycleAction((cur) => ({ ...cur, [id]: e.target.value as CycleAction }))}
                    >
                      <option value="keep">Keep Active</option>
                      <option value="closeRefresh">Close Refresh &amp; New</option>
                      <option value="new">Create New Cycle</option>
                    </select>
                    <div className="pm-console__cyclehint">
                      {action === 'new'
                        ? (active ? <>closes <b>{active.name}</b>, opens a fresh one</> : <>opens the first cycle</>)
                        : action === 'closeRefresh'
                          ? (active ? <>locks the current refresh, starts a new one in <b>{active.name}</b></> : <span className="pm-console__warn">no active cycle</span>)
                          : (active ? <>refreshes <b>{active.name}</b></> : <span className="pm-console__warn">no active cycle</span>)}
                    </div>
                  </td>
                  <td>
                    {run ? (
                      <div className="pm-steps">
                        {STAGES.map((k) => <StageChip key={k} label={STAGE_LABEL[k]} stage={run.stages[k]} now={now} />)}
                      </div>
                    ) : <span className="sx-dim">Waiting</span>}
                    {run?.message && (
                      <div className={`pm-console__msg ${run.status === 'failed' ? 'pm-console__msg--bad' : ''}`}>{run.message}</div>
                    )}
                  </td>
                  <td className="pm-console__rescol">
                    {run?.result ? (
                      <div className="pm-console__res">
                        <span><b>{num(run.result.products)}</b> products</span>
                        <span><b>{num(run.result.workingItems)}</b> items</span>
                        {run.result.carriedForward > 0 && <span className="sx-dim">{num(run.result.carriedForward)} carried</span>}
                      </div>
                    ) : <span className="sx-dim">—</span>}
                  </td>
                  <td className="pm-console__timecol sx-num">{run ? dur(runMs(run, now)) : '—'}</td>
                  <td className="pm-console__actcol">
                    <div className="pm-console__acts">
                      {run?.status === 'failed' && (
                        <button className="pm-btn pm-btn--ghost pm-btn--sm" disabled={running} onClick={() => retry(s)} title="Retry from the failed stage">
                          <i className="bi bi-arrow-clockwise" /> Retry
                        </button>
                      )}
                      {run?.status === 'confirm' && (
                        <button className="pm-btn pm-btn--ghost pm-btn--sm" disabled={running} onClick={() => forceContinue(s)} title="Clear pending items and open a fresh cycle">
                          Force close
                        </button>
                      )}
                      {run && run.log.length > 0 && (
                        <button
                          className="pm-console__chev"
                          aria-label={isOpen ? 'Hide log' : 'Show log'}
                          onClick={() => setExpanded((cur) => {
                            const next = new Set(cur)
                            if (next.has(id)) next.delete(id)
                            else next.add(id)
                            return next
                          })}
                        >
                          <i className={`bi ${isOpen ? 'bi-chevron-up' : 'bi-chevron-down'}`} />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>,
                isOpen && run ? (
                  <tr key={`${id}-log`} className="pm-console__logrow">
                    <td colSpan={9}>
                      <div className="pm-console__logwrap">
                        <div className="pm-console__log">
                          {run.log.map((l, i) => (
                            <div className="pm-console__logline" key={`${l.at}-${i}`}>
                              <span className="pm-console__logt">{clock(l.at)}</span>
                              <span>{l.text}</span>
                            </div>
                          ))}
                        </div>
                        {run.result && (
                          <div className="pm-console__breakdown">
                            <div><span>Products</span><b>{num(run.result.products)}</b></div>
                            <div><span>Included</span><b>{num(run.result.included)}</b></div>
                            <div><span>Excluded</span><b>{num(run.result.excluded)}</b></div>
                            <div><span>Working items</span><b>{num(run.result.workingItems)}</b></div>
                            <div><span>Carried forward</span><b>{num(run.result.carriedForward)}</b></div>
                            {STAGES.map((k) => (
                              <div key={k}><span>{STAGE_LABEL[k]}</span><b>{dur(stageMs(run.stages[k], now))}</b></div>
                            ))}
                          </div>
                        )}
                      </div>
                    </td>
                  </tr>
                ) : null,
              ]
            })}
          </tbody>
        </table>
      )}
    </div>
  )
}
