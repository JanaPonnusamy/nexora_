import { useCallback, useEffect, useState } from 'react'
import type { ControlCenter, LiveStore, SyncHistoryRow } from '../../types/sync'
import { useAsyncData } from '../../hooks/useAsyncData'
import { syncService } from '../../services/syncService'
import { storeService } from '../../services/storeService'
import { tenantService } from '../../services/tenantService'
import { ErrorState } from '../common/ErrorState'
import { TableSkeleton } from '../common/TableSkeleton'
import { SyncStatusBadge } from './SyncBadges'
import { SxButton, SxCard, SxCardBody, SxCardHead, SxProgress } from './ui'

type DashboardStore = ControlCenter['stores'][number] & {
  tenant_id?: string
  tenant_name: string
  live?: LiveStore
}

type ActionNotice = {
  tone: 'info' | 'danger' | 'success' | 'warning'
  text: string
}

async function fetchControlCenter() {
  const [cc, storeList, tenantList, schedules, history] = await Promise.all([
    syncService.controlCenter(),
    storeService.list(),
    tenantService.list(),
    syncService.schedules(),
    syncService.history(),
  ])
  return { cc, storeList, tenantList, schedules, history }
}

function timeOnly(iso: string | null): string {
  if (!iso) return '-'
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function shortDateTime(iso: string | null): string {
  if (!iso) return '-'
  const parsed = new Date(iso)
  if (Number.isNaN(parsed.getTime())) return iso
  return parsed.toLocaleString([], { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function compactRows(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(n >= 100_000_000 ? 0 : 1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(n >= 100_000 ? 0 : 1)}K`
  return n.toLocaleString()
}

function storePriority(row: DashboardStore): number {
  if (row.live) return 0
  if ((row.status ?? '').toUpperCase() === 'FAILED') return 1
  if ((row.agent_status ?? '').toLowerCase() !== 'online') return 2
  return 3
}

function storeStatus(row: DashboardStore): string {
  if (row.live?.status === 'PAUSED') return 'PAUSED'
  if (row.live) return 'RUNNING'
  if ((row.status ?? '').toUpperCase() === 'FAILED') return 'FAILED'
  return row.agent_status || row.status || 'Offline'
}

function activityTone(status: string | null): 'success' | 'danger' | 'indigo' | 'warning' | 'muted' {
  const value = (status ?? '').toUpperCase()
  if (value === 'COMPLETED') return 'success'
  if (value === 'FAILED') return 'danger'
  if (value === 'RUNNING') return 'indigo'
  if (value === 'PENDING' || value === 'QUEUED') return 'warning'
  return 'muted'
}

function activityAbbr(status: string | null): string {
  const value = (status ?? '').toUpperCase()
  if (value === 'COMPLETED') return 'OK'
  if (value === 'FAILED') return 'FLD'
  if (value === 'RUNNING') return 'RUN'
  if (value === 'PENDING') return 'PND'
  if (value === 'QUEUED') return 'Q'
  if (value === 'PAUSED') return 'PAU'
  return value.slice(0, 3) || '---'
}

export function ControlCenterTab() {
  const { data, isLoading, error, reload } = useAsyncData(fetchControlCenter)
  const [dynamic, setDynamic] = useState<{ cc: ControlCenter; history: SyncHistoryRow[]; liveRows: LiveStore[]; refreshedAt: number } | null>(null)
  const [busyAction, setBusyAction] = useState<string | null>(null)
  const [notice, setNotice] = useState<ActionNotice | null>(null)

  const refreshLiveState = useCallback(async () => {
    const [cc, history, liveRows] = await Promise.all([
      syncService.controlCenter(),
      syncService.history(),
      syncService.live(),
    ])
    setDynamic({ cc, history, liveRows, refreshedAt: Date.now() })
  }, [])

  useEffect(() => {
    let active = true
    const tick = async () => {
      try {
        const [cc, history, liveRows] = await Promise.all([
          syncService.controlCenter(),
          syncService.history(),
          syncService.live(),
        ])
        if (!active) return
        setDynamic({ cc, history, liveRows, refreshedAt: Date.now() })
      } catch {
        /* keep last good snapshot */
      }
    }
    void tick()
    const id = setInterval(tick, 3000)
    return () => {
      active = false
      clearInterval(id)
    }
  }, [])

  if (isLoading) return <TableSkeleton rows={8} columns={8} />
  if (error || !data) return <ErrorState description={error ?? 'Failed to load control center'} onRetry={reload} />

  const cc = dynamic?.cc ?? data.cc
  const history = dynamic?.history ?? data.history
  const liveRows = dynamic?.liveRows ?? []
  const schedules = data.schedules

  const tenantNames = new Map(data.tenantList.map((tenant) => [tenant.tenant_id, tenant.tenant_name]))
  const storeTenant = new Map(data.storeList.map((store) => [store.store_id, store.tenant_id]))
  const liveMap = Object.fromEntries(liveRows.map((row) => [row.store_id, row]))

  const stores: DashboardStore[] = (
    cc.stores
      .map((store) => {
        const tenantId = storeTenant.get(store.store_id)
        return {
          ...store,
          tenant_id: tenantId,
          tenant_name: (tenantId && tenantNames.get(tenantId)) || '-',
          live: liveMap[store.store_id],
        }
      })
      .sort((a, b) => {
        const diff = storePriority(a) - storePriority(b)
        if (diff !== 0) return diff
        return (a.store_code || '').localeCompare(b.store_code || '')
      })
  )

  const actionableStores = stores.filter((store) => store.tenant_id)
  const failedToday = cc.kpis.failed_today
  const runningNow = Math.max(cc.kpis.sync_running, liveRows.length)
  const totalRowsToday = history.reduce((sum, row) => sum + (row.rows || 0), 0)
  const latestFailedStores = Array.from(new Map(
    history
      .filter((row) => row.status === 'FAILED' && row.store_id)
      .map((row) => [row.store_id as string, row]),
  ).values())
  const recentActivity = history.slice(0, 5)
  const runningJobs = [...liveRows]
    .sort((a, b) => (b.updated_at ?? '').localeCompare(a.updated_at ?? ''))
    .slice(0, 5)
  const upcomingSchedules = schedules
    .filter((schedule) => schedule.is_enabled)
    .sort((a, b) => (a.start_time ?? '').localeCompare(b.start_time ?? ''))
    .slice(0, 5)
  const lastCompleted = history.find((row) => row.status === 'COMPLETED')
  const latestSyncAt = stores
    .map((store) => store.last_sync)
    .filter((value): value is string => Boolean(value))
    .sort((a, b) => b.localeCompare(a))[0] ?? null
  const healthLabel = failedToday > 0 ? 'Attention needed' : 'Healthy'
  const pausedCount = stores.filter((store) => store.live?.status === 'PAUSED').length
  const retryCount = latestFailedStores
    .map((row) => stores.find((store) => store.store_id === row.store_id))
    .filter((store): store is DashboardStore => Boolean(store?.tenant_id))
    .length

  const runAction = async (key: string, work: () => Promise<number>, done: (count: number) => ActionNotice) => {
    setBusyAction(key)
    setNotice(null)
    try {
      const count = await work()
      const nextNotice = done(count)
      setNotice(nextNotice.tone === 'danger' ? nextNotice : null)
      await Promise.all([reload(), refreshLiveState()])
    } catch (err) {
      setNotice({
        tone: 'danger',
        text: err instanceof Error ? err.message : 'Action failed.',
      })
    } finally {
      setBusyAction(null)
    }
  }

  const syncAll = () => runAction(
    'sync-all',
    async () => {
      await Promise.all(actionableStores.map((store) =>
        syncService.createTask({
          tenant_id: store.tenant_id as string,
          store_id: store.store_id,
          execution_type: 'FULL',
          sync_mode: 'FULL',
        })))
      return actionableStores.length
    },
    (count) => ({ tone: 'success', text: `Queued full sync for ${count} store${count === 1 ? '' : 's'}.` }),
  )

  const pauseAll = () => runAction(
    'pause',
    async () => {
      const ids = liveRows.map((row) => row.store_id)
      if (ids.length === 0) return 0
      await syncService.control(ids, 'PAUSE')
      return ids.length
    },
    (count) => ({ tone: 'info', text: count > 0 ? `Pause sent to ${count} running store${count === 1 ? '' : 's'}.` : 'No running syncs to pause.' }),
  )

  const stopAll = () => runAction(
    'stop',
    async () => {
      const ids = liveRows.map((row) => row.store_id)
      if (ids.length === 0) return 0
      await syncService.control(ids, 'STOP')
      return ids.length
    },
    (count) => ({ tone: 'warning', text: count > 0 ? `Stop sent to ${count} running store${count === 1 ? '' : 's'}.` : 'No running syncs to stop.' }),
  )

  const resumeAll = () => runAction(
    'resume',
    async () => {
      const resumable = stores.filter((store) => (store.live?.status === 'PAUSED' || (store.status ?? '').toUpperCase() === 'QUEUED') && store.tenant_id)
      if (resumable.length === 0) return 0
      await Promise.all(resumable.map((store) =>
        syncService.createTask({
          tenant_id: store.tenant_id as string,
          store_id: store.store_id,
          execution_type: 'FULL',
          sync_mode: 'FULL',
        })))
      return resumable.length
    },
    (count) => ({ tone: 'success', text: count > 0 ? `Queued restart for ${count} paused or queued store${count === 1 ? '' : 's'}.` : 'No paused or queued stores to resume.' }),
  )

  const retryFailed = () => runAction(
    'retry',
    async () => {
      const retryTargets = latestFailedStores
        .map((row) => stores.find((store) => store.store_id === row.store_id))
        .filter((store): store is DashboardStore => Boolean(store?.tenant_id))
      if (retryTargets.length === 0) return 0
      await Promise.all(retryTargets.map((store) =>
        syncService.createTask({
          tenant_id: store.tenant_id as string,
          store_id: store.store_id,
          execution_type: 'FULL',
          sync_mode: 'FULL',
        })))
      return retryTargets.length
    },
    (count) => ({ tone: count > 0 ? 'success' : 'info', text: count > 0 ? `Queued retry for ${count} failed store${count === 1 ? '' : 's'}.` : 'No failed stores available to retry.' }),
  )

  const syncOne = (store: DashboardStore) => runAction(
    `sync-${store.store_id}`,
    async () => {
      if (!store.tenant_id) return 0
      await syncService.createTask({
        tenant_id: store.tenant_id,
        store_id: store.store_id,
        execution_type: 'FULL',
        sync_mode: 'FULL',
      })
      return 1
    },
    (count) => ({
      tone: count > 0 ? 'success' : 'info',
      text: count > 0
        ? `Queued full sync for ${store.store_name || store.store_code || 'store'}.`
        : `Unable to queue sync for ${store.store_name || store.store_code || 'store'}.`,
    }),
  )

  return (
    <div className="sx-command">
      {notice && <div className={`sx-alert sx-alert--${notice.tone}`}>{notice.text}</div>}

      <section className="sx-command__kpis">
        <div className={`sx-kpi ${failedToday > 0 ? 'sx-tone-warning' : 'sx-tone-success'}`}>
          <span className="sx-kpi__icon"><i className="bi bi-arrow-repeat" aria-hidden="true" /></span>
          <div className="sx-kpi__body">
            <div className="sx-kpi__label">Running</div>
            <div className="sx-kpi__value">{runningNow}</div>
            <div className="sx-kpi__sub">{healthLabel}</div>
          </div>
        </div>
        <div className="sx-kpi sx-tone-success">
          <span className="sx-kpi__icon"><i className="bi bi-building-check" aria-hidden="true" /></span>
          <div className="sx-kpi__body">
            <div className="sx-kpi__label">Online</div>
            <div className="sx-kpi__value">{cc.kpis.stores_online}/{stores.length}</div>
            <div className="sx-kpi__sub">stores healthy</div>
          </div>
        </div>
        <div className="sx-kpi sx-tone-muted">
          <span className="sx-kpi__icon"><i className="bi bi-stack" aria-hidden="true" /></span>
          <div className="sx-kpi__body">
            <div className="sx-kpi__label">Queue</div>
            <div className="sx-kpi__value">{cc.kpis.queued}</div>
            <div className="sx-kpi__sub">awaiting agent</div>
          </div>
        </div>
        <div className={`sx-kpi ${failedToday > 0 ? 'sx-tone-danger' : 'sx-tone-muted'}`}>
          <span className="sx-kpi__icon"><i className="bi bi-exclamation-octagon" aria-hidden="true" /></span>
          <div className="sx-kpi__body">
            <div className="sx-kpi__label">Failed</div>
            <div className="sx-kpi__value">{failedToday}</div>
            <div className="sx-kpi__sub">today</div>
          </div>
        </div>
        <div className="sx-kpi sx-tone-muted">
          <span className="sx-kpi__icon"><i className="bi bi-graph-up-arrow" aria-hidden="true" /></span>
          <div className="sx-kpi__body">
            <div className="sx-kpi__label">Processed</div>
            <div className="sx-kpi__value">{compactRows(totalRowsToday)}</div>
            <div className="sx-kpi__sub">rows processed</div>
          </div>
        </div>
        <div className="sx-kpi sx-tone-muted">
          <span className="sx-kpi__icon"><i className="bi bi-clock-history" aria-hidden="true" /></span>
          <div className="sx-kpi__body">
            <div className="sx-kpi__label">Last Sync</div>
            <div className="sx-kpi__value">{latestSyncAt ? timeOnly(latestSyncAt) : '-'}</div>
            <div className="sx-kpi__sub">{latestSyncAt ? shortDateTime(latestSyncAt).split(',')[0] : 'no completed run'}</div>
          </div>
        </div>
        <div className="sx-kpi sx-tone-violet">
          <span className="sx-kpi__icon"><i className="bi bi-pause-circle" aria-hidden="true" /></span>
          <div className="sx-kpi__body">
            <div className="sx-kpi__label">Paused</div>
            <div className="sx-kpi__value">{pausedCount}</div>
            <div className="sx-kpi__sub">jobs waiting</div>
          </div>
        </div>
      </section>

      <section className="sx-command__main">
        <SxCard className="sx-pane sx-pane--stores">
          <SxCardHead title="Live Store Grid" icon="bi-hdd-stack" sub={`${stores.length} stores`} />
          <SxCardBody flush>
            <div className="sx-storegrid">
              <div className="sx-storegrid__head">
                <span>Store</span>
                <span>Status</span>
                <span>Current Table</span>
                <span>Progress</span>
                <span>Speed</span>
                <span>Last Sync</span>
                <span>Action</span>
              </div>
              <div className="sx-storegrid__body">
                {stores.length === 0 ? (
                  <div className="sx-storegrid__empty">No stores available.</div>
                ) : stores.map((store) => (
                  <div className="sx-storegrid__row" key={store.store_id}>
                    <div className="sx-storegrid__store">
                      <span className="sx-storegrid__line">
                        <span className="sx-storegrid__code">{store.store_code}</span>
                        <span className="sx-storegrid__name" title={store.store_name}>{store.store_name}</span>
                      </span>
                    </div>
                    <div><SyncStatusBadge status={storeStatus(store)} compact /></div>
                    <div className="sx-storegrid__table">{store.live?.current_table ?? store.current_activity ?? '-'}</div>
                    <div className="sx-storegrid__progress">
                      {store.live ? (
                        <>
                          <SxProgress value={store.live.progress_pct} />
                          <span className="sx-storegrid__pct">{store.live.progress_pct}%</span>
                        </>
                      ) : <span className="sx-dim">Idle</span>}
                    </div>
                    <div className="sx-storegrid__speed">
                      {store.live?.speed_rows_sec ? `${store.live.speed_rows_sec.toLocaleString()}/s` : '-'}
                    </div>
                    <div className="sx-storegrid__sync">{shortDateTime(store.last_sync)}</div>
                    <div className="sx-storegrid__action">
                      <SxButton
                        sm
                        variant="ghost"
                        icon="bi-play-fill"
                        busy={busyAction === `sync-${store.store_id}`}
                        disabled={!store.tenant_id}
                        title={store.tenant_id ? `Sync ${store.store_name || store.store_code}` : 'Tenant not available'}
                        onClick={() => syncOne(store)}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </SxCardBody>
        </SxCard>

        <SxCard className="sx-pane sx-pane--actions">
          <SxCardHead title="Quick Actions" icon="bi-lightning-charge" sub="Immediate control" />
          <SxCardBody>
            <div className="sx-command__actions">
              <div className="sx-command__actions-bar">
                <div className="sx-command__action-stat">
                  <span>Ready</span>
                  <strong>{actionableStores.length}</strong>
                </div>
                <div className="sx-command__action-stat">
                  <span>Running</span>
                  <strong>{runningNow}</strong>
                </div>
                <div className="sx-command__action-stat">
                  <span>Retry</span>
                  <strong>{retryCount}</strong>
                </div>
                <div className="sx-command__action-stat">
                  <span>Pause</span>
                  <strong>{pausedCount}</strong>
                </div>
              </div>
              <div className="sx-command__actions-grid">
                <SxButton variant="primary" icon="bi-play-fill" busy={busyAction === 'sync-all'} onClick={syncAll}>Full Sync</SxButton>
                <SxButton variant="warning" icon="bi-pause-fill" busy={busyAction === 'pause'} onClick={pauseAll}>Pause Jobs</SxButton>
                <SxButton variant="success" icon="bi-play-circle" busy={busyAction === 'resume'} onClick={resumeAll}>Resume Queue</SxButton>
                <SxButton variant="ghost" icon="bi-arrow-repeat" busy={busyAction === 'retry'} onClick={retryFailed}>Retry Failed</SxButton>
              </div>
              <div className="sx-command__danger">
                <div className="sx-command__danger-label">Danger Zone</div>
                <SxButton variant="danger" icon="bi-stop-fill" busy={busyAction === 'stop'} onClick={stopAll}>Stop All</SxButton>
              </div>
            </div>
          </SxCardBody>
        </SxCard>
      </section>

      <section className="sx-command__feeds">
        <SxCard className="sx-pane sx-pane--jobs">
          <SxCardHead title="Running Jobs" icon="bi-broadcast" sub={`${runningJobs.length} live`} />
          <SxCardBody>
            <div className="sx-feed">
              {runningJobs.length === 0 ? (
                <div className="sx-feed__summary">
                  <div className="sx-feed__summary-row">
                    <span className="sx-feed__summary-label">Queue</span>
                    <strong>{cc.kpis.queued}</strong>
                  </div>
                  <div className="sx-feed__summary-row">
                    <span className="sx-feed__summary-label">Workers</span>
                    <strong>{cc.kpis.stores_online}</strong>
                  </div>
                  <div className="sx-feed__summary-row">
                    <span className="sx-feed__summary-label">Last Run</span>
                    <strong>{lastCompleted ? timeOnly(lastCompleted.started_at) : '-'}</strong>
                  </div>
                  <div className="sx-feed__summary-row">
                    <span className="sx-feed__summary-label">Failed</span>
                    <strong>{failedToday}</strong>
                  </div>
                </div>
              ) : runningJobs.map((row) => (
                <div className="sx-feed__row" key={row.execution_id}>
                  <div className="sx-feed__main">
                    <span className="sx-feed__title">{row.store_code ?? 'Store'} / {row.current_table ?? '-'}</span>
                    <span className="sx-feed__meta">{row.progress_pct}% / {row.speed_rows_sec > 0 ? `${row.speed_rows_sec.toLocaleString()}/s` : '-'}</span>
                  </div>
                  <span className="sx-feed__time">{timeOnly(row.updated_at)}</span>
                </div>
              ))}
            </div>
          </SxCardBody>
        </SxCard>

        <SxCard className="sx-pane">
          <SxCardHead title="Recent Activity" icon="bi-clock-history" sub="Last 5 events" />
          <SxCardBody>
            <div className="sx-feed">
              {recentActivity.length === 0 ? (
                <div className="sx-feed__empty">No activity yet.</div>
              ) : recentActivity.map((row) => (
                <div className="sx-feed__row" key={row.sync_id}>
                  <div className="sx-feed__inline">
                    <span className="sx-feed__title">{row.store_name ?? row.store_code ?? 'Store'}</span>
                    <span className={`sx-feed__status sx-feed__status--${activityTone(row.status)}`}>{activityAbbr(row.status)}</span>
                    <span className="sx-feed__op">{row.sync_mode === 'FULL' ? 'Full' : row.sync_mode === 'UPSERT' ? 'Upsert' : (row.sync_mode ?? '-')}</span>
                  </div>
                  <span className="sx-feed__time">{timeOnly(row.started_at)}</span>
                </div>
              ))}
            </div>
          </SxCardBody>
        </SxCard>

        <SxCard className="sx-pane">
          <SxCardHead title="Upcoming Schedules" icon="bi-calendar-event" sub={`${upcomingSchedules.length} shown`} />
          <SxCardBody>
            <div className="sx-feed">
              {upcomingSchedules.length === 0 ? (
                <div className="sx-feed__empty">No schedules configured.</div>
              ) : upcomingSchedules.map((schedule) => (
                <div className="sx-feed__row" key={schedule.schedule_id}>
                  <div className="sx-feed__inline">
                    <span className="sx-feed__title">{schedule.store_code ?? 'ALL'}</span>
                    <span className="sx-feed__op">{schedule.sync_mode === 'FULL' ? 'Full' : (schedule.sync_mode ?? '-')}</span>
                  </div>
                  <span className="sx-feed__time">{timeOnly(schedule.start_time)}</span>
                </div>
              ))}
            </div>
          </SxCardBody>
        </SxCard>
      </section>
    </div>
  )
}
