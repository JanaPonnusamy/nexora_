import { Fragment, useCallback, useEffect, useState } from 'react'
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

// Running / Online / Offline only; how fresh the data is shows in the
// Last Bill / Last GRN columns.
function storeStatus(row: DashboardStore): string {
  if (row.live || row.is_syncing) return 'RUNNING'
  return (row.agent_status ?? '').toLowerCase() === 'online' ? 'Online' : 'Offline'
}

// 09:29 for today, else 04/11 19:23; a date-only stamp (GRN) shows just 04/11.
function stamp(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const time = d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
  const today = d.toDateString() === new Date().toDateString()
  const dateOnly = d.getHours() === 0 && d.getMinutes() === 0 && d.getSeconds() === 0
  const day = today ? 'Today' : d.toLocaleDateString('en-GB', { day: '2-digit', month: '2-digit' })
  if (dateOnly) return day
  return today ? time : `${day} ${time}`
}

function RefCell({ no, at }: { no: string | number | null | undefined; at: string | null | undefined }) {
  if (no == null || no === '') return <div className="sx-storegrid__ref sx-dim">-</div>
  const when = stamp(at)
  return (
    <div className="sx-storegrid__ref" title={at ? `${no} · ${new Date(at).toLocaleString()}` : String(no)}>
      <span className="sx-storegrid__refno">{no}</span>
      {when && <span className="sx-storegrid__reftime">{when}</span>}
    </div>
  )
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
      .sort((a, b) => a.tenant_name.localeCompare(b.tenant_name)
        || storePriority(a) - storePriority(b)
        || (a.store_code || '').localeCompare(b.store_code || ''))
  )
  // Grouped per tenant, like the Legacy Order console (stores are tenant-sorted above).
  const tenantGroups: { name: string; stores: DashboardStore[] }[] = []
  for (const store of stores) {
    const last = tenantGroups[tenantGroups.length - 1]
    if (last && last.name === store.tenant_name) last.stores.push(store)
    else tenantGroups.push({ name: store.tenant_name, stores: [store] })
  }

  const actionableStores = stores.filter((store) => store.tenant_id)
  const recentActivity = history.slice(0, 5)
  const tenantOfStore = (storeId: string | null) => {
    const tenantId = storeId ? storeTenant.get(storeId) : undefined
    return (tenantId && tenantNames.get(tenantId)) || null
  }


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
                <span>Tenant</span>
                <span>Status</span>
                <span>Current Table</span>
                <span>Progress</span>
                <span>Speed</span>
                <span>Last Sync</span>
                <span>Last Bill</span>
                <span>Last GRN</span>
                <span>Action</span>
              </div>
              <div className="sx-storegrid__body">
                {stores.length === 0 ? (
                  <div className="sx-storegrid__empty">No stores available.</div>
                ) : tenantGroups.map((group) => (
                  <Fragment key={group.name}>
                  {tenantGroups.length > 1 && (
                    <div className="sx-storegrid__group">{group.name}<span>{group.stores.length} store{group.stores.length === 1 ? '' : 's'}</span></div>
                  )}
                  {group.stores.map((store) => (
                  <div className="sx-storegrid__row" key={store.store_id}>
                    <div className="sx-storegrid__store">
                      <span className="sx-storegrid__line">
                        <span className="sx-storegrid__code">{store.store_code}</span>
                        <span className="sx-storegrid__name" title={store.store_name}>{store.store_name}</span>
                      </span>
                    </div>
                    <div className="sx-storegrid__tenant" title={store.tenant_name}>{store.tenant_name}</div>
                    <div>
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
                    <RefCell no={store.last_bill_no} at={store.last_sale_bill_at} />
                    <RefCell no={store.last_grn_no} at={store.last_grn_at} />
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
                  </Fragment>
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
              ) : recentActivity.map((row) => {
                const tenant = tenantOfStore(row.store_id)
                return (
                <div className="sx-feed__row" key={row.sync_id}>
                  <div className="sx-feed__inline">
                    <span className="sx-feed__title">
                      {row.store_name ?? row.store_code ?? 'Store'}
                      {tenant && <span className="sx-feed__tenant"> · {tenant}</span>}
                    </span>
                    <span className={`sx-feed__status sx-feed__status--${activityTone(row.status)}`}>{activityAbbr(row.status)}</span>
                    <span className="sx-feed__op">{row.sync_mode === 'FULL' ? 'Full' : row.sync_mode === 'UPSERT' ? 'Upsert' : (row.sync_mode ?? '-')}</span>
                  </div>
                  <span className="sx-feed__time">{timeOnly(row.started_at)}</span>
                </div>
                )
              })}
            </div>
          </SxCardBody>
        </SxCard>
      </section>
    </div>
  )
}
