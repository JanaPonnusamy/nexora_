import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
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
import '../legacy-order/legacy-order.css'
import { FilterSelect } from '../../design-system/components/FilterBar'

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
type RefreshInfo = { count: number; latestName: string | null; latestNo: number | null; latestAt: string | null }

const POLL_MS = 2500
// The agent picks up a queued task on its own ~60s poll cycle (store_agent's
// SYNC_POLL_SECONDS), then works through tables sequentially - a store with a
// few large tables can legitimately run well past 4 minutes. A fixed
// wall-clock deadline on the whole sync was firing on real, still-progressing
// work. Instead we only time out when progress genuinely stalls: no change in
// completed_tables (or status) for STALL_TIMEOUT_MS. SYNC_MAX_MS is just an
// outer sanity net for a truly wedged execution, not the thing meant to fire
// in normal operation.
const STALL_TIMEOUT_MS = 90_000
const SYNC_MAX_MS = 30 * 60_000
const DEFAULT_ROLLING = '90'
const DEFAULT_MIN = '13'
const DEFAULT_MAX = '18'
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
    // "Heartbeat" here is the execution's own progress signal (status +
    // completed_tables), not a separate agent ping — it's already returned by
    // /api/sync/history/{id} on every poll, so no new endpoint is needed to
    // tell a genuinely stalled execution apart from one still working through
    // its table list.
    let lastSignature = ''
    let lastProgressAt = start
    const tick = async () => {
      if (cancelled()) return resolve('cancelled')
      try {
        const sum = await syncService.executionSummary(execId)
        if (cancelled()) return resolve('cancelled')
        const total = sum.total_tables ?? 0
        const done = sum.completed_tables ?? 0
        onProgress(total > 0 ? Math.min(100, Math.round((done / total) * 100)) : null)
        const signature = `${sum.status ?? ''}:${done}:${sum.failed_tables ?? 0}:${sum.rows_uploaded ?? 0}`
        if (signature !== lastSignature) {
          lastSignature = signature
          lastProgressAt = Date.now()
        }
        const t = terminal(sum.status)
        if (t) return resolve(t)
      } catch {
        /* transient (agent mid-write / network blip) — keep polling, doesn't
         * reset the stall clock since it's not evidence of real progress */
      }
      const now = Date.now()
      if (now - lastProgressAt > STALL_TIMEOUT_MS) return resolve('timeout')
      if (now - start > SYNC_MAX_MS) return resolve('timeout')
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

// --- Cross-navigation run store ---------------------------------------------
//
// Sync/Cycle/Refresh keep running server-side once started; the earlier
// version tracked their progress in plain component state, which React
// destroys the instant you navigate to another screen — so switching away
// mid-run and back showed a blank "Waiting" console even though the backend
// was still (or already done) working. Module-scope state survives
// navigation (it's not tied to a component instance), so this page's
// subscribers just re-read whatever's still in flight when it remounts —
// exactly like the legacy Sync screen's live status.
type RunsState = Record<string, StoreRun>
type BatchState = { start: number; end: number | null } | null
type ConsoleSnapshot = { runs: RunsState; running: boolean; batch: BatchState }

const consoleStore = (() => {
  let snapshot: ConsoleSnapshot = { runs: {}, running: false, batch: null }
  const listeners = new Set<() => void>()
  const notify = () => listeners.forEach((l) => l())
  // Reference-counted: a lone per-store action (Force close, Retry) can now
  // run concurrently with a bulk batch. Without this, whichever one finishes
  // first flips `running` off and re-enables the toolbar while the other is
  // still working.
  let inFlight = 0
  return {
    subscribe(listener: () => void) {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },
    getSnapshot: () => snapshot,
    setRuns(updater: (prev: RunsState) => RunsState) {
      snapshot = { ...snapshot, runs: updater(snapshot.runs) }
      notify()
    },
    updateRun(id: string, fn: (r: StoreRun) => StoreRun) {
      snapshot = { ...snapshot, runs: { ...snapshot.runs, [id]: fn(snapshot.runs[id] ?? blankRun(id)) } }
      notify()
    },
    beginOp() {
      inFlight += 1
      if (!snapshot.running) { snapshot = { ...snapshot, running: true }; notify() }
    },
    endOp() {
      inFlight = Math.max(0, inFlight - 1)
      if (inFlight === 0 && snapshot.running) { snapshot = { ...snapshot, running: false }; notify() }
    },
    setBatch(updater: (prev: BatchState) => BatchState) {
      snapshot = { ...snapshot, batch: updater(snapshot.batch) }
      notify()
    },
    /** Stores whose VPL actually generated in the in-flight batch — survives
     *  navigation the same way, so consolidation still fires correctly even
     *  if the user wasn't watching when the batch finished. */
    refreshedIds: new Set<string>(),
  }
})()

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
  /** Ticked = close the active cycle and open a fresh one on run; unticked =
   *  refresh inside whichever cycle is already active. */
  const [newCycle, setNewCycle] = useState<Set<string>>(new Set())
  const [rollingDays, setRollingDays] = useState(DEFAULT_ROLLING)
  const [minDays, setMinDays] = useState(DEFAULT_MIN)
  const [maxDays, setMaxDays] = useState(DEFAULT_MAX)
  const [useExistingData, setUseExistingData] = useState(false)
  const isDefaultParams = rollingDays === DEFAULT_ROLLING && minDays === DEFAULT_MIN && maxDays === DEFAULT_MAX
  const resetParams = useCallback(() => {
    setRollingDays(DEFAULT_ROLLING)
    setMinDays(DEFAULT_MIN)
    setMaxDays(DEFAULT_MAX)
  }, [])

  /** Per-store overrides of rolling/min/max — set via a store card's gear
   *  panel. A store with no entry here just follows the global toolbar values. */
  const [storeOverride, setStoreOverride] = useState<Record<string, { rolling: string; min: string; max: string }>>({})
  const [settingsOpenFor, setSettingsOpenFor] = useState<string | null>(null)
  const [infoOpenFor, setInfoOpenFor] = useState<string | null>(null)
  /** Must be ticked before "Force close" is clickable — the action is
   *  destructive (pending items are cleared, not carried forward). */
  const [forceConfirm, setForceConfirm] = useState<Set<string>>(new Set())

  const effectiveDays = useCallback((storeId: string) => storeOverride[storeId] ?? {
    rolling: rollingDays, min: minDays, max: maxDays,
  }, [storeOverride, rollingDays, minDays, maxDays])

  const patchOverride = (storeId: string, patch: Partial<{ rolling: string; min: string; max: string }>) => {
    setStoreOverride((cur) => ({ ...cur, [storeId]: { ...effectiveDays(storeId), ...patch } }))
  }
  const clearOverride = (storeId: string) => {
    setStoreOverride((cur) => {
      const next = { ...cur }
      delete next[storeId]
      return next
    })
  }

  const parseParamsFor = useCallback((storeId: string): Params | null => {
    const { rolling, min, max } = effectiveDays(storeId)
    const minN = Number(min), maxN = Number(max), rollN = Number(rolling)
    if (Number.isNaN(minN) || Number.isNaN(maxN) || minN >= maxN) return null
    return { rolling: Number.isNaN(rollN) ? undefined : rollN, min: minN, max: maxN }
  }, [effectiveDays])

  /** The store the network purchase quantity is calculated FOR once every
   *  selected store's VPL is built. Empty = do not consolidate. */
  const [warehouseId, setWarehouseId] = useState('')
  const [consolidating, setConsolidating] = useState(false)

  // Subscribed to the module-level store (see consoleStore above) instead of
  // component state, so an in-flight run's progress isn't lost when this page
  // unmounts — navigate away and back and it's exactly where it left off.
  const { runs, running, batch } = useSyncExternalStore(consoleStore.subscribe, consoleStore.getSnapshot)

  // Ticks only while work is in flight, so live durations count up without
  // re-rendering an idle page.
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    if (!running) return
    const t = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(t)
  }, [running])

  // Never flips true: polling and the pipeline itself are meant to keep going
  // in the background across navigation now (see consoleStore) — this stays
  // only as the signature pollSync/runPipeline already expect.
  const cancelled = useRef(false)

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

  // Prunes selections/runs for stores that dropped out of this tenant's list —
  // NOT a blanket reset. `tenantStores` gets a fresh array identity on every
  // remount (stores are refetched), so wiping `runs` here would erase live
  // progress just from navigating back to this page.
  useEffect(() => {
    const ids = new Set(tenantStores.map((s) => s.store_id))
    setSelected((cur) => new Set([...cur].filter((id) => ids.has(id))))
    setNewCycle((cur) => new Set([...cur].filter((id) => ids.has(id))))
    consoleStore.setRuns((prev) => Object.fromEntries(Object.entries(prev).filter(([id]) => ids.has(id))))
  }, [tenantStores])

  const activeCycleOf = useCallback(
    (storeId: string) => cyclesByStore[storeId]?.find((c) => (c.status ?? '').toUpperCase() === 'ACTIVE') ?? null,
    [cyclesByStore],
  )

  const update = useCallback((id: string, fn: (r: StoreRun) => StoreRun) => {
    consoleStore.updateRun(id, fn)
  }, [])

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
    // The refresh to lock before generating the next one — never set anymore
    // since the "Close Refresh & New" action was dropped from the UI in favour
    // of a plain New Cycle checkbox; kept so a future re-add doesn't need to
    // touch the refresh stage below.
    const refreshToClose: string | undefined = undefined
    const wantNew = newCycle.has(id)
    if (startIdx <= STAGES.indexOf('cycle')) {
      update(id, (r) => beginStage(r, 'cycle', 'Resolving cycle…'))
      try {
        const cycles = await procurementService.cycles(tenantId, id)
        const active = cycles.find((c) => (c.status ?? '').toUpperCase() === 'ACTIVE') ?? null

        let target: Cycle
        if (!wantNew) {
          if (!active) {
            update(id, (r) => failStage(r, 'cycle', 'No active cycle — tick “Create new cycle” to open one'))
            return
          }
          target = active
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
      consoleStore.refreshedIds.add(id)
      update(id, (r) => {
        const next = doneStage({ ...r, result }, 'refresh',
          `Refresh completed — ${num(result.products)} products, ${num(result.workingItems)} working items`)
        return { ...next, status: 'completed', endedAt: Date.now() }
      })
    } catch (e) {
      update(id, (r) => failStage(r, 'refresh', errMsg(e)))
    }
  }, [tenantId, actingUser, newCycle, useExistingData, update])

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

  /** Run every selected store, each with its own effective params (override,
   *  or the global toolbar values when it has none). */
  const runBatch = async () => {
    const targets = tenantStores.filter((s) => selected.has(s.store_id))
    if (!targets.length) return say('danger', 'Select at least one store')
    const invalid = targets.filter((s) => !parseParamsFor(s.store_id))
    if (invalid.length) return say('danger', `Min days must be less than Max days — ${invalid.map((s) => s.store_name).join(', ')}`)

    cancelled.current = false
    consoleStore.setRuns(() => Object.fromEntries(targets.map((s) => [s.store_id, blankRun(s.store_id)])))
    consoleStore.setBatch(() => ({ start: Date.now(), end: null }))
    consoleStore.beginOp()
    try {
      // Parallel, and isolated: one store's failure cannot reject the batch.
      consoleStore.refreshedIds.clear()
      await Promise.allSettled(targets.map((s) => runPipeline(s, 'sync', parseParamsFor(s.store_id)!)))
      // Consolidate only the stores whose VPL actually generated (runPipeline
      // records a failure on the store rather than throwing, so a settled promise
      // does NOT mean the store succeeded).
      await consolidate([...consoleStore.refreshedIds])
    } finally {
      consoleStore.endOp()
      consoleStore.setBatch((b) => (b ? { ...b, end: Date.now() } : b))
      reloadContext()
    }
  }

  /** Run a single store from its own card's Run button — independent of the
   *  checkbox selection used for a bulk run. */
  const runOne = async (store: Store) => {
    const params = parseParamsFor(store.store_id)
    if (!params) return say('danger', `${store.store_name}: Min days must be less than Max days`)
    cancelled.current = false
    consoleStore.setRuns((prev) => ({ ...prev, [store.store_id]: blankRun(store.store_id) }))
    consoleStore.setBatch(() => ({ start: Date.now(), end: null }))
    consoleStore.beginOp()
    try {
      consoleStore.refreshedIds.delete(store.store_id)
      await runPipeline(store, 'sync', params)
      if (consoleStore.refreshedIds.has(store.store_id)) await consolidate([store.store_id])
    } finally {
      consoleStore.endOp()
      consoleStore.setBatch((b) => (b ? { ...b, end: Date.now() } : b))
      reloadContext()
    }
  }

  /** Retry ONE store, resuming at the stage that failed. A refresh-stage retry
   *  reuses the cycle already resolved, so it cannot close a second cycle. */
  const retry = async (store: Store) => {
    const run = runs[store.store_id]
    if (!run) return
    const params = parseParamsFor(store.store_id)
    if (!params) return say('danger', `${store.store_name}: Min days must be less than Max days`)
    const from: StageKey =
      run.stages.sync.status === 'failed' ? 'sync'
        : run.stages.cycle.status === 'failed' ? 'cycle'
          : 'refresh'

    cancelled.current = false
    consoleStore.beginOp()
    try {
      await runPipeline(store, from, params, { cycleId: run.cycleId })
    } finally {
      consoleStore.endOp()
      reloadContext()
    }
  }

  /** Confirmed close-with-pending: re-run the cycle stage with force. */
  const forceContinue = async (store: Store) => {
    const params = parseParamsFor(store.store_id)
    if (!params) return say('danger', `${store.store_name}: Min days must be less than Max days`)
    cancelled.current = false
    consoleStore.beginOp()
    try {
      await runPipeline(store, 'cycle', params, { force: true })
      setForceConfirm((cur) => { const next = new Set(cur); next.delete(store.store_id); return next })
    } finally {
      consoleStore.endOp()
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
  const runCounts = useMemo(() => {
    const list = Object.values(runs)
    return {
      running: list.filter((r) => r.status === 'running').length,
      failed: list.filter((r) => r.status === 'failed').length,
      completed: list.filter((r) => r.status === 'completed').length,
    }
  }, [runs])
  const sortedRuns = useMemo(
    () => tenantStores.map((s) => ({ store: s, run: runs[s.store_id] })).filter((r): r is { store: Store; run: StoreRun } => Boolean(r.run)),
    [tenantStores, runs],
  )
  const infoStore = infoOpenFor ? tenantStores.find((s) => s.store_id === infoOpenFor) : undefined
  const infoRun = infoOpenFor ? runs[infoOpenFor] : undefined

  return (
    <div className="legacy-order pm-console">
      <header className="lo-header">
        <div>
          <h1><i className="bi bi-arrow-repeat" /> Cycle &amp; Refresh Console</h1>
          <div className="lo-kpis">
            <span>{tenantStores.length} Stores</span>
            <span className="lo-kpi-ok"><span className="lo-dot lo-dot-ok" />{runCounts.completed} Completed</span>
            <span><span className="lo-dot lo-dot-fail" />{runCounts.failed} Failed</span>
            <span><span className="lo-dot lo-dot-run" />{runCounts.running} Running</span>
          </div>
        </div>
        <div className="lo-actions">
          <FilterSelect ariaLabel="Tenant" value={tenantId} onChange={setTenantId} disabled={running}>
            {tenants.length === 0 && <option value="">Loading…</option>}
            {tenants.map((t) => <option key={t.tenant_id} value={t.tenant_id}>{t.tenant_name}</option>)}
          </FilterSelect>
          <button className="lo-btn" onClick={reloadContext} disabled={running} title="Reload"><i className="bi bi-arrow-clockwise" /></button>
          <span className="lo-badge">Procurement</span>
        </div>
      </header>

      {banner && <div className={banner.kind === 'success' ? 'lo-success' : 'lo-error'} role="alert">{banner.text}</div>}

      <section className="lo-card">
        <div className="lo-section-title">
          <div>
            <h2>Store operations</h2>
            <p className="lo-note">
              Sync → Cycle → Refresh (Decision Engine + VPL). Defaults: {DEFAULT_ROLLING} rolling / {DEFAULT_MIN} min days / {DEFAULT_MAX} max days —
              override per store with the gear icon on its card.
            </p>
          </div>
        </div>

        <div className="lo-row" style={{ marginBottom: '0.85rem' }}>
          <label><span>Rolling days</span><input value={rollingDays} onChange={(e) => setRollingDays(e.target.value)} disabled={running} /></label>
          <label><span>Min days</span><input value={minDays} onChange={(e) => setMinDays(e.target.value)} disabled={running} /></label>
          <label><span>Max days</span><input value={maxDays} onChange={(e) => setMaxDays(e.target.value)} disabled={running} /></label>
          <button type="button" className="lo-btn" disabled={running || isDefaultParams} onClick={resetParams} title={`Restore Rolling/Min/Max to their defaults (${DEFAULT_ROLLING} / ${DEFAULT_MIN} / ${DEFAULT_MAX})`}>
            <i className="bi bi-arrow-counterclockwise" /> Reset to default
          </button>
          <label className="pm-console__opt" title="Skip the sync stage and refresh from the data already synced">
            <input type="checkbox" checked={useExistingData} onChange={(e) => setUseExistingData(e.target.checked)} disabled={running} />
            <span>Use Existing Store Data</span>
          </label>
          <label className="lo-grow" title="Every store's VPL is merged into one network grid, and the purchase quantity is calculated FOR this store">
            <span>Buying warehouse</span>
            <select value={warehouseId} onChange={(e) => setWarehouseId(e.target.value)} disabled={running}>
              <option value="">Skip consolidation</option>
              {tenantStores.map((s) => <option key={s.store_id} value={s.store_id}>{s.store_name}</option>)}
            </select>
          </label>
        </div>

        <div className="lo-row" style={{ marginBottom: '0.85rem' }}>
          <label style={{ flexDirection: 'row', alignItems: 'center', gap: '0.4rem' }}>
            <input
              type="checkbox"
              aria-label="Select all"
              checked={allSelected}
              disabled={running}
              onChange={() => setSelected(allSelected ? new Set() : new Set(tenantStores.map((s) => s.store_id)))}
            />
            <span>Select all</span>
          </label>
          <span className="sx-dim"><b>{workload.stores}</b> selected{workload.withData > 0 && <> · ≈ <b>{num(workload.products)}</b> products</>}</span>
          <button type="button" className="lo-btn lo-btn-primary" disabled={running || selected.size === 0} onClick={runBatch}>
            <i className="bi bi-play-fill" /> {consolidating ? 'Consolidating…' : running ? 'Running…' : `Run ${selected.size || ''} selected`.replace('  ', ' ')}
          </button>
        </div>

        {showSummary && (
          <section className={`pm-console__summary ${summary.failed ? 'pm-console__summary--warn' : ''}`} style={{ marginBottom: '0.85rem' }}>
            <div className="pm-console__sumitem"><b>{summary.completed}</b><span>of {summary.selected} completed</span></div>
            {summary.failed > 0 && <div className="pm-console__sumitem pm-console__sumitem--bad"><b>{summary.failed}</b><span>failed</span></div>}
            <div className="pm-console__sumitem"><b>{num(summary.products)}</b><span>products</span></div>
            <div className="pm-console__sumitem"><b>{num(summary.workingItems)}</b><span>working items</span></div>
            <div className="pm-console__sumitem"><b>{num(summary.carried)}</b><span>carried forward</span></div>
            <div className="pm-console__sumitem"><b>{dur(summary.duration)}</b><span>total</span></div>
          </section>
        )}

        {settingsOpenFor && (
          <div className="pm-console__settings-scrim" onClick={() => setSettingsOpenFor(null)} />
        )}

        {tenantStores.length === 0 ? (
          <EmptyState icon="bi-shop" title="No stores" description="This tenant has no active stores." />
        ) : (
          <div className="lo-store-cards">
            {tenantStores.map((s) => {
              const id = s.store_id
              const run = runs[id]
              const active = activeCycleOf(id)
              const info = refreshInfo[id]
              const wantsNewCycle = newCycle.has(id)
              const days = effectiveDays(id)
              const hasOverride = Boolean(storeOverride[id])
              const cardState = run?.status === 'running' ? 'running' : run?.status === 'failed' ? 'failed' : run?.status === 'completed' ? 'completed' : 'idle'
              return (
                <article className="lo-op-card" key={id} data-state={cardState}>
                  <div className="lo-op-head">
                    <input
                      type="checkbox"
                      aria-label={`Select ${s.store_name}`}
                      checked={selected.has(id)}
                      disabled={running}
                      onChange={() => setSelected((cur) => {
                        const next = new Set(cur)
                        if (next.has(id)) next.delete(id); else next.add(id)
                        return next
                      })}
                    />
                    <strong>{s.store_code}</strong>
                    <span className="lo-op-icons">
                      <button type="button" className="lo-icon-btn" title="Per-store days override" aria-label={`${s.store_name} settings`} onClick={() => setSettingsOpenFor(settingsOpenFor === id ? null : id)}><i className="bi bi-gear" /></button>
                      <button type="button" className="lo-icon-btn" title="Store information" aria-label={`${s.store_name} info`} onClick={() => setInfoOpenFor(id)}><i className="bi bi-info-circle" /></button>
                    </span>
                  </div>
                  <p className="lo-op-owner">{s.store_name}</p>

                  <small className="lo-op-conn">
                    {active ? <>{active.name} <span className="pm-badge pm-badge--active">Active</span></> : 'No open cycle'}
                    {' · '}{info?.latestName ? <>{info.latestNo != null ? `Refresh ${info.latestNo}` : info.latestName} ({refreshWhen(info.latestAt)})</> : 'No refresh yet'}
                  </small>
                  <label className="pm-console__newcycle" title={wantsNewCycle ? 'Closes the active cycle and opens a fresh one' : 'Refreshes inside the currently active cycle'}>
                    <input
                      type="checkbox"
                      aria-label={`Create new cycle for ${s.store_name}`}
                      checked={wantsNewCycle}
                      disabled={running}
                      onChange={() => setNewCycle((cur) => {
                        const next = new Set(cur)
                        if (next.has(id)) next.delete(id); else next.add(id)
                        return next
                      })}
                    />
                    <span>New cycle</span>
                  </label>

                  {settingsOpenFor === id && (
                    <div className="lo-op-settings">
                      <label><span>Rolling</span><input aria-label={`${s.store_name} rolling days`} value={days.rolling} onChange={(e) => patchOverride(id, { rolling: e.target.value })} disabled={running} /></label>
                      <label><span>Min days</span><input aria-label={`${s.store_name} minimum days`} value={days.min} onChange={(e) => patchOverride(id, { min: e.target.value })} disabled={running} /></label>
                      <label><span>Max days</span><input aria-label={`${s.store_name} maximum days`} value={days.max} onChange={(e) => patchOverride(id, { max: e.target.value })} disabled={running} /></label>
                      {!parseParamsFor(id) && <small className="lo-invalid">Min must be less than Max</small>}
                      <div className="lo-op-settings-actions">
                        <button type="button" className="lo-btn" disabled={!hasOverride} onClick={() => clearOverride(id)}>Reset to global</button>
                      </div>
                    </div>
                  )}

                  <div className="lo-op-progress">
                    {run && (
                      <div className="pm-steps">
                        {STAGES.map((k) => <StageChip key={k} label={STAGE_LABEL[k]} stage={run.stages[k]} now={now} />)}
                      </div>
                    )}
                    {run?.status === 'failed' && <small className="lo-invalid">Failed — see info for details</small>}
                    {run?.result && (
                      <small className="lo-cell-sub">
                        {num(run.result.products)} products · {num(run.result.workingItems)} items
                        {run.result.carriedForward > 0 && <> · {num(run.result.carriedForward)} carried</>}
                        {' · '}{dur(runMs(run, now))}
                      </small>
                    )}
                  </div>

                  {run?.status === 'failed' ? (
                    <button type="button" className="lo-btn lo-op-process lo-op-retry" disabled={running} onClick={() => retry(s)}>
                      <i className="bi bi-arrow-clockwise" /> Retry
                    </button>
                  ) : run?.status === 'confirm' ? (
                    <div className="pm-console__confirm">
                      <label className="pm-console__confirmcheck">
                        <input
                          type="checkbox"
                          aria-label={`Confirm clearing pending items for ${s.store_name}`}
                          checked={forceConfirm.has(id)}
                          onChange={() => setForceConfirm((cur) => {
                            const next = new Set(cur)
                            if (next.has(id)) next.delete(id); else next.add(id)
                            return next
                          })}
                        />
                        <span>Clear pending items &amp; close (see info)</span>
                      </label>
                      <button type="button" className="lo-btn lo-op-process" disabled={!forceConfirm.has(id)} onClick={() => forceContinue(s)}>
                        Force close
                      </button>
                    </div>
                  ) : run?.status === 'running' ? (
                    <button type="button" className="lo-btn lo-op-process" disabled>
                      <i className="bi bi-hourglass-split" /> Processing…
                    </button>
                  ) : (
                    <button type="button" className="lo-btn lo-btn-primary lo-op-process" disabled={running || !parseParamsFor(id)} onClick={() => runOne(s)}>
                      <i className="bi bi-play-fill" /> Run {s.store_code}
                    </button>
                  )}
                </article>
              )
            })}
          </div>
        )}
      </section>

      {infoStore && (
        <div className="lo-drawer-backdrop" role="presentation" onClick={() => setInfoOpenFor(null)}>
          <aside className="lo-drawer" role="dialog" aria-label={`${infoStore.store_name} information`} onClick={(e) => e.stopPropagation()}>
            <div className="lo-drawer-head">
              <h3>Store information — {infoStore.store_name}</h3>
              <button type="button" className="lo-icon-btn" aria-label="Close" onClick={() => setInfoOpenFor(null)}>×</button>
            </div>
            <div className="lo-drawer-body">
              <h4>Refresh window</h4>
              <dl className="lo-meta">
                <div><dt>Rolling</dt><dd>{effectiveDays(infoStore.store_id).rolling}</dd></div>
                <div><dt>Min days</dt><dd>{effectiveDays(infoStore.store_id).min}</dd></div>
                <div><dt>Max days</dt><dd>{effectiveDays(infoStore.store_id).max}</dd></div>
                <div><dt>Source</dt><dd>{storeOverride[infoStore.store_id] ? 'Per-store override' : 'Global default'}</dd></div>
              </dl>
              <h4>Latest run</h4>
              <dl className="lo-meta">
                <div><dt>Status</dt><dd>{infoRun ? <span className={`lo-chip lo-chip-${infoRun.status === 'completed' ? 'success' : infoRun.status}`}>{infoRun.status}</span> : '—'}</dd></div>
                <div><dt>Cycle</dt><dd>{infoRun?.cycleName ?? activeCycleOf(infoStore.store_id)?.name ?? '—'}</dd></div>
                <div><dt>Duration</dt><dd>{infoRun ? dur(runMs(infoRun, now)) : '—'}</dd></div>
                <div><dt>Message</dt><dd>{infoRun?.message ?? '—'}</dd></div>
              </dl>
              {infoRun?.result && (
                <>
                  <h4>Result</h4>
                  <dl className="lo-meta">
                    <div><dt>Products</dt><dd>{num(infoRun.result.products)}</dd></div>
                    <div><dt>Included</dt><dd>{num(infoRun.result.included)}</dd></div>
                    <div><dt>Excluded</dt><dd>{num(infoRun.result.excluded)}</dd></div>
                    <div><dt>Working items</dt><dd>{num(infoRun.result.workingItems)}</dd></div>
                    <div><dt>Carried forward</dt><dd>{num(infoRun.result.carriedForward)}</dd></div>
                  </dl>
                </>
              )}
              {infoRun?.log && infoRun.log.length > 0 && (
                <>
                  <h4>Log</h4>
                  <ol className="lo-drawer-log">
                    {infoRun.log.map((entry, index) => <li key={`${entry.at}-${index}`}><time>{clock(entry.at)}</time>{entry.text}</li>)}
                  </ol>
                </>
              )}
            </div>
          </aside>
        </div>
      )}

      <section className="lo-card lo-activity">
        <div className="lo-section-title">
          <div><h2>Task log</h2><p className="lo-note">Live progress from every store run this session.</p></div>
          <span className="lo-count">{runCounts.running} running</span>
        </div>
        <div className="lo-job-list">
          {sortedRuns.map(({ store, run }) => (
            <article className="lo-job" key={store.store_id}>
              <div className="lo-job-head">
                <strong>{store.store_name} · {STAGES.find((k) => run.stages[k].status === 'running') ? STAGE_LABEL[STAGES.find((k) => run.stages[k].status === 'running')!] : 'Pipeline'}</strong>
                <span className={`lo-chip lo-chip-${run.status === 'completed' ? 'success' : run.status}`}>{run.status}</span>
              </div>
              <div className="pm-steps">
                {STAGES.map((k) => <StageChip key={k} label={STAGE_LABEL[k]} stage={run.stages[k]} now={now} />)}
              </div>
              {run.message && <p>{run.message}</p>}
              {run.log.length > 0 && (
                <details className="lo-log">
                  <summary>{run.log.length} log entries</summary>
                  <ol>{run.log.map((entry, index) => <li key={`${entry.at}-${index}`}><time>{clock(entry.at)}</time>{entry.text}</li>)}</ol>
                </details>
              )}
            </article>
          ))}
          {!sortedRuns.length && <div className="lo-empty">Run a store to see live task activity.</div>}
        </div>
      </section>
    </div>
  )
}
