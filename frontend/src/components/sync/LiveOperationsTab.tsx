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
  const [cc, storeList, tenantList, history] = await Promise.all([
    syncService.controlCenter(),
    storeService.list(),
    tenantService.list(),
    syncService.history(),
  ])
  return { cc, storeList, tenantList, history }
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
  // Agent heartbeat and sync executions can look healthy while no fresh sale
  // bill has actually landed in 30+ minutes -- surface that as a strong,
  // distinct warning rather than folding it into a plain "Online".
  if (row.sale_bill_stale) return 'STALE_SALES'
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

function staleBillTooltip(row: DashboardStore): string {
  return row.last_sale_bill_minutes_ago == null
    ? 'STRONG WARNING: no synced sale bill found for this store at all.'
    : `STRONG WARNING: last sale bill synced ${row.last_sale_bill_minutes_ago} minutes ago (over 30-minute threshold).`
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



export function LiveOperationsTab() {
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
    const id = setInterval(tick, 2000)
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
  const recentActivity = history.slice(0, 5)


  /* ---- Actions ---- */
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

      {/* ---- Live Store Grid + Quick Actions ---- */}
      <section className="sx-command__main">
        <SxCard className="sx-pane sx-pane--stores">
          <SxCardHead
            title="Live Store Grid"
            icon="bi-hdd-stack"
            sub={`${stores.length} stores`}
            action={
              <SxButton
                variant="primary"
                icon="bi-play-fill"
                busy={busyAction === 'sync-all'}
                disabled={actionableStores.length === 0}
                onClick={syncAll}
              >
                Full Sync
              </SxButton>
            }
          />
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
                    <div title={store.sale_bill_stale ? staleBillTooltip(store) : undefined}>
                      <SyncStatusBadge status={storeStatus(store)} compact />
                    </div>
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
      </section>


      {/* ---- Recent Activity Feed ---- */}
      <section className="sx-command__feeds">
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
      </section>
    </div>
  )
}
