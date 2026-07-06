import { useEffect, useMemo, useState } from 'react'
import type { ControlCenter, LiveStore, SyncHistoryRow } from '../../types/sync'
import { useAsyncData } from '../../hooks/useAsyncData'
import { syncService } from '../../services/syncService'
import { storeService } from '../../services/storeService'
import { tenantService } from '../../services/tenantService'
import { ErrorState } from '../common/ErrorState'
import { TableSkeleton } from '../common/TableSkeleton'
import { ConnectionType, SyncStatusBadge, SyncTypeBadge } from './SyncBadges'
import { DonutChart } from '../dashboard/DonutChart'
import { formatDateTime } from '../../utils/format'
import {
  SxCard, SxCardHead, SxCardBody, SxStat, SxChip, SxButton, SxSegmented,
  SxSearch, SxSelect, SxPager, SxProgress, SxLive, SxLegend, SxTable,
} from './ui'

const PAGE_SIZE = 10
const CONNECTIONS = ['All', 'LAN', 'WiFi', 'Internet']
const SYNC_TYPES = [
  { label: 'All', value: 'All' },
  { label: 'Upsert', value: 'UPSERT' },
  { label: 'Rolling', value: 'ROLLING_WINDOW' },
]

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

function pct(part: number, total: number): string {
  if (!total) return '0%'
  return `${((part / total) * 100).toFixed(0)}%`
}
function fmtNum(n: number | null | undefined): string {
  return n == null ? '—' : n.toLocaleString()
}
function fmtEta(seconds: number | null): string {
  if (seconds == null || seconds <= 0) return '—'
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  if (m >= 60) return `${Math.floor(m / 60)}h ${m % 60}m`
  return m > 0 ? `${m}m ${s}s` : `${s}s`
}
function timeOnly(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function DonutPanel({ title, segments }: { title: string; segments: { label: string; value: number; color: string }[] }) {
  return (
    <SxCard className="h-100">
      <SxCardHead title={title} />
      <SxCardBody>
        <div className="sx-donut">
          <DonutChart segments={segments.map((s) => ({ ...s }))} size={108} thickness={14} />
          <SxLegend segments={segments} />
        </div>
      </SxCardBody>
    </SxCard>
  )
}

export function ControlCenterTab() {
  const { data, isLoading, error, reload } = useAsyncData(fetchControlCenter)
  const [tenantFilter, setTenantFilter] = useState('all')
  const [connectionFilter, setConnectionFilter] = useState('All')
  const [syncTypeFilter, setSyncTypeFilter] = useState('All')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)
  const [view, setView] = useState<'table' | 'card'>('table')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [busy, setBusy] = useState(false)
  const [dynamic, setDynamic] = useState<{ cc: ControlCenter; history: SyncHistoryRow[] } | null>(null)
  const [liveMap, setLiveMap] = useState<Record<string, LiveStore>>({})

  useEffect(() => {
    let active = true
    const tick = async () => {
      try {
        const [cc, hist, liveRows] = await Promise.all([
          syncService.controlCenter(),
          syncService.history(),
          syncService.live(),
        ])
        if (!active) return
        setDynamic({ cc, history: hist })
        setLiveMap(Object.fromEntries(liveRows.map((r) => [r.store_id, r])))
      } catch {
        /* keep last good state */
      }
    }
    void tick()
    const id = setInterval(tick, 2000)
    return () => { active = false; clearInterval(id) }
  }, [])

  const tenantNames = useMemo(
    () => new Map((data?.tenantList ?? []).map((t) => [t.tenant_id, t.tenant_name])),
    [data],
  )
  const storeTenant = useMemo(
    () => new Map((data?.storeList ?? []).map((s) => [s.store_id, s.tenant_id])),
    [data],
  )

  const rows = useMemo(() => {
    const stores = (dynamic?.cc ?? data?.cc)?.stores ?? []
    return stores.map((store) => {
      const tenantId = storeTenant.get(store.store_id)
      const live = liveMap[store.store_id]
      return {
        ...store,
        tenant_name: (tenantId && tenantNames.get(tenantId)) || '—',
        tenant_id: tenantId,
        live,
        is_syncing: store.is_syncing || Boolean(live),
      }
    })
  }, [data, dynamic, liveMap, storeTenant, tenantNames])

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase()
    return rows.filter((row) => {
      if (tenantFilter !== 'all' && row.tenant_id !== tenantFilter) return false
      if (connectionFilter !== 'All' && row.connection_type !== connectionFilter) return false
      if (syncTypeFilter !== 'All') {
        const t = (row.live?.sync_type ?? '').toUpperCase()
        if (syncTypeFilter === 'ROLLING_WINDOW' ? !t.includes('ROLL') : t !== 'UPSERT') return false
      }
      if (query && !`${row.store_code} ${row.store_name}`.toLowerCase().includes(query)) return false
      return true
    })
  }, [rows, tenantFilter, connectionFilter, syncTypeFilter, search])

  async function runSyncSelected() {
    const targets = rows.filter((r) => selected.has(r.store_id) && r.tenant_id)
    if (targets.length === 0) return
    setBusy(true)
    try {
      await Promise.all(targets.map((r) =>
        syncService.createTask({ tenant_id: r.tenant_id as string, store_id: r.store_id, execution_type: 'FULL', sync_mode: 'FULL' })))
    } finally { setBusy(false) }
  }

  async function control(action: 'PAUSE' | 'STOP') {
    if (selected.size === 0) return
    setBusy(true)
    try { await syncService.control([...selected], action) } finally { setBusy(false) }
  }

  async function runOne(storeId: string, tenantId?: string) {
    if (!tenantId) return
    setBusy(true)
    try {
      await syncService.createTask({ tenant_id: tenantId, store_id: storeId, execution_type: 'FULL', sync_mode: 'FULL' })
    } finally { setBusy(false) }
  }

  if (isLoading) return <TableSkeleton rows={8} columns={12} />
  if (error || !data) return <ErrorState description={error ?? 'Failed to load control center'} onRetry={reload} />

  const { storeList, tenantList, schedules } = data
  const cc = dynamic?.cc ?? data.cc
  const history = dynamic?.history ?? data.history
  const { kpis } = cc
  const totalStores = storeList.length
  const liveList = Object.values(liveMap)

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const clampedPage = Math.min(page, totalPages - 1)
  const pageRows = filtered.slice(clampedPage * PAGE_SIZE, clampedPage * PAGE_SIZE + PAGE_SIZE)
  const rangeStart = filtered.length === 0 ? 0 : clampedPage * PAGE_SIZE + 1
  const rangeEnd = Math.min(filtered.length, clampedPage * PAGE_SIZE + PAGE_SIZE)

  const online = kpis.stores_online
  const offline = kpis.stores_offline
  const syncing = Math.max(kpis.sync_running, liveList.length)
  const connCounts = CONNECTIONS.slice(1).map((c) => ({ type: c, count: rows.filter((r) => r.connection_type === c).length }))

  const success = history.filter((h) => h.status === 'COMPLETED').length
  const failure = history.filter((h) => h.status === 'FAILED').length
  const totalRecords = history.reduce((a, h) => a + (h.rows ?? 0), 0)
  const successRate = success + failure ? ((success / (success + failure)) * 100).toFixed(0) : '100'
  const avgSpeed = liveList.length ? Math.round(liveList.reduce((a, l) => a + l.speed_rows_sec, 0) / liveList.length) : 0
  const upcoming = schedules.filter((s) => s.is_enabled)

  const upsertSyncs = liveList.filter((l) => (l.sync_type ?? '').toUpperCase() === 'UPSERT').length
  const rollingSyncs = liveList.filter((l) => (l.sync_type ?? '').toUpperCase().includes('ROLL')).length
  const notSyncing = totalStores - liveList.length

  const allVisibleSelected = pageRows.length > 0 && pageRows.every((r) => selected.has(r.store_id))
  const toggleAll = () => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (allVisibleSelected) pageRows.forEach((r) => next.delete(r.store_id))
      else pageRows.forEach((r) => next.add(r.store_id))
      return next
    })
  }
  const toggleOne = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })

  return (
    <div className="sx-stack">
      {/* KPI row */}
      <div className="row row-cols-2 row-cols-md-3 row-cols-xl-6 g-3">
        <div className="col"><SxStat icon="bi-building" tone="indigo" value={tenantList.length} label="Total Tenants" sub="Active" /></div>
        <div className="col"><SxStat icon="bi-shop" tone="teal" value={totalStores} label="Total Stores" sub="Registered" /></div>
        <div className="col"><SxStat icon="bi-wifi" tone="info" value={online} label="Stores Online" sub={pct(online, totalStores)} /></div>
        <div className="col"><SxStat icon="bi-arrow-repeat" tone="violet" value={syncing} label="Stores Syncing" sub={pct(syncing, totalStores)} /></div>
        <div className="col"><SxStat icon="bi-check-circle" tone="success" value={kpis.completed_today} label="Completed Today" sub="Success" /></div>
        <div className="col"><SxStat icon="bi-exclamation-triangle" tone={kpis.failed_today ? 'danger' : 'muted'} value={kpis.failed_today} label="Failed Today" sub={kpis.failed_today ? pct(kpis.failed_today, kpis.completed_today + kpis.failed_today) : '0%'} /></div>
      </div>

      {/* Active Sync Details */}
      <SxCard>
        <SxCardHead title="Active Sync Details" icon="bi-activity"
          sub={<SxChip tone="indigo">{liveList.length} active</SxChip>}
          action={<SxLive label="live · 2s" />} />
        <SxCardBody flush>
          <SxTable>
            <thead>
              <tr>
                <th>Store</th><th>Current Table</th><th>Chunk</th>
                <th className="sx-num">Processed</th><th className="sx-num">Remaining</th>
                <th className="sx-num">Speed</th><th>ETA</th><th>Last Update</th>
              </tr>
            </thead>
            <tbody>
              {liveList.length === 0 ? (
                <tr><td colSpan={8} className="sx-table__empty">No active syncs right now.</td></tr>
              ) : liveList.map((l) => (
                <tr key={l.execution_id}>
                  <td>
                    <span className={`sx-sdot sx-sdot--${l.status === 'PAUSED' ? 'paused' : 'running'}`} />
                    <span className="sx-strong">{l.store_code}</span>
                    <span className="sx-dim"> — {l.store_name}</span>
                  </td>
                  <td><div className="sx-rowlabel"><span className="sx-rowlabel__main">{l.current_table ?? '—'}</span><SyncTypeBadge value={l.sync_type} /></div></td>
                  <td className="sx-strong">{l.chunk_no ?? '—'}{l.total_chunks ? ` / ${l.total_chunks}` : ''}</td>
                  <td className="sx-num">{fmtNum(l.rows_processed)}</td>
                  <td className="sx-num">{fmtNum(l.rows_remaining)}</td>
                  <td className="sx-num" style={{ color: 'var(--sx-success)', fontWeight: 650 }}>{l.speed_rows_sec > 0 ? `${l.speed_rows_sec.toLocaleString()}/s` : '—'}</td>
                  <td>{fmtEta(l.eta_seconds)}</td>
                  <td className="sx-dim">{timeOnly(l.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </SxTable>
        </SxCardBody>
      </SxCard>

      {/* Toolbar */}
      <SxCard>
        <SxCardBody>
          <div className="sx-toolbar">
            <label className="d-inline-flex align-items-center gap-2 small fw-semibold mb-0">
              <input type="checkbox" className="form-check-input mt-0" checked={allVisibleSelected} onChange={toggleAll} aria-label="Select all" />
              Select ({selected.size})
            </label>
            <SxSelect value={tenantFilter} ariaLabel="Tenant" onChange={(v) => { setTenantFilter(v); setPage(0) }}>
              <option value="all">All Tenants</option>
              {tenantList.map((t) => <option key={t.tenant_id} value={t.tenant_id}>{t.tenant_name}</option>)}
            </SxSelect>
            <SxSegmented ariaLabel="Connection" value={connectionFilter}
              onChange={(v) => { setConnectionFilter(v); setPage(0) }}
              options={CONNECTIONS.map((c) => ({ label: c, value: c }))} />
            <SxSegmented ariaLabel="Sync type" value={syncTypeFilter}
              onChange={(v) => { setSyncTypeFilter(v); setPage(0) }} options={SYNC_TYPES} />
            <div className="ms-auto d-flex gap-2">
              <SxButton variant="primary" icon="bi-play-fill" busy={busy} disabled={selected.size === 0} onClick={runSyncSelected}>Sync</SxButton>
              <SxButton variant="warning" icon="bi-pause-fill" disabled={busy || selected.size === 0} onClick={() => control('PAUSE')}>Pause</SxButton>
              <SxButton variant="danger" icon="bi-stop-fill" disabled={busy || selected.size === 0} onClick={() => control('STOP')}>Stop</SxButton>
            </div>
          </div>
        </SxCardBody>
      </SxCard>

      {/* Store sync status */}
      <SxCard>
        <SxCardHead title={`Store Sync Status`} icon="bi-hdd-network"
          sub={`${filtered.length} stores`}
          action={
            <div className="d-flex align-items-center gap-2">
              <SxSegmented ariaLabel="View" value={view} onChange={setView}
                options={[{ label: 'Table', value: 'table' }, { label: 'Cards', value: 'card' }]} />
              <SxSearch value={search} onChange={(v) => { setSearch(v); setPage(0) }} placeholder="Search store…" ariaLabel="Search store" />
            </div>
          } />
        <SxCardBody flush>
          {view === 'table' ? (
            <SxTable>
              <thead>
                <tr>
                  <th><input type="checkbox" className="form-check-input" checked={allVisibleSelected} onChange={toggleAll} aria-label="Select page" /></th>
                  <th>Store</th><th>Connection</th><th>Sync Type</th><th>Current Table</th>
                  <th className="sx-num">Rows</th><th>Progress</th><th className="sx-num">Speed</th>
                  <th>Last Sync</th><th>Status</th><th className="sx-num">Run</th>
                </tr>
              </thead>
              <tbody>
                {pageRows.length === 0 ? (
                  <tr><td colSpan={11} className="sx-table__empty">No stores match the current filters.</td></tr>
                ) : pageRows.map((row) => {
                  const live = row.live
                  return (
                    <tr key={row.store_id}>
                      <td><input type="checkbox" className="form-check-input" checked={selected.has(row.store_id)} onChange={() => toggleOne(row.store_id)} aria-label={`Select ${row.store_name}`} /></td>
                      <td><div className="sx-rowlabel"><span className="sx-rowlabel__main">{row.store_code}</span><span className="sx-rowlabel__sub">{row.store_name}</span></div></td>
                      <td><ConnectionType value={row.connection_type} /></td>
                      <td><SyncTypeBadge value={live?.sync_type ?? null} /></td>
                      <td>{live?.current_table ? <span className="sx-strong">{live.current_table}</span> : <span className="sx-dim">—</span>}</td>
                      <td className="sx-num">
                        {live && live.total_rows ? <span>{live.rows_processed.toLocaleString()} <span className="sx-dim">/ {live.total_rows.toLocaleString()}</span></span>
                          : live ? live.rows_processed.toLocaleString() : <span className="sx-dim">—</span>}
                      </td>
                      <td style={{ minWidth: 120 }}>
                        {live ? <><SxProgress value={live.progress_pct} /><div className="sx-dim" style={{ fontSize: '0.72rem', marginTop: 2 }}>{live.progress_pct}%</div></>
                          : <span className="sx-dim" style={{ fontSize: '0.78rem' }}>0%</span>}
                      </td>
                      <td className="sx-num">{live && live.speed_rows_sec > 0 ? <span style={{ color: 'var(--sx-success)', fontWeight: 650 }}>{live.speed_rows_sec.toLocaleString()}</span> : <span className="sx-dim">—</span>}</td>
                      <td className="sx-dim" style={{ fontSize: '0.8rem' }}>{formatDateTime(row.last_sync)}</td>
                      <td><SyncStatusBadge status={live ? (live.status === 'PAUSED' ? 'QUEUED' : 'Syncing') : row.status} /></td>
                      <td className="sx-num">
                        <SxButton variant="primary" sm icon="bi-play-fill" disabled={!row.tenant_id || busy} title={row.tenant_id ? 'Queue full sync' : 'Tenant unknown'} onClick={() => runOne(row.store_id, row.tenant_id)} />
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </SxTable>
          ) : (
            <div className="p-3">
              <div className="row row-cols-1 row-cols-md-2 row-cols-xl-3 g-3">
                {pageRows.length === 0 ? (
                  <p className="sx-dim small mb-0">No stores match the current filters.</p>
                ) : pageRows.map((row) => {
                  const live = row.live
                  return (
                    <div className="col" key={row.store_id}>
                      <div className="sx-card" style={{ padding: '0.9rem' }}>
                        <div className="d-flex align-items-start justify-content-between mb-2">
                          <div className="sx-rowlabel"><span className="sx-rowlabel__main">{row.store_code}</span><span className="sx-rowlabel__sub">{row.store_name}</span></div>
                          <SyncStatusBadge status={live ? 'Syncing' : row.status} />
                        </div>
                        <div className="d-flex align-items-center gap-2 mb-2">
                          <ConnectionType value={row.connection_type} />
                          <SyncTypeBadge value={live?.sync_type ?? null} />
                        </div>
                        {live ? (
                          <>
                            <div className="d-flex justify-content-between small mb-1">
                              <span className="sx-strong">{live.current_table}</span>
                              <span className="sx-dim">{live.progress_pct}%</span>
                            </div>
                            <SxProgress value={live.progress_pct} />
                            <div className="d-flex justify-content-between small sx-dim mt-1">
                              <span>{live.rows_processed.toLocaleString()} rows</span>
                              <span>{live.speed_rows_sec > 0 ? `${live.speed_rows_sec.toLocaleString()}/s · ETA ${fmtEta(live.eta_seconds)}` : '—'}</span>
                            </div>
                          </>
                        ) : <div className="sx-dim small">Idle · last sync {formatDateTime(row.last_sync)}</div>}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
          <SxPager rangeStart={rangeStart} rangeEnd={rangeEnd} total={filtered.length} page={clampedPage} totalPages={totalPages} onPage={setPage} noun="stores" />
        </SxCardBody>
      </SxCard>

      {/* Insight panels */}
      <div className="row row-cols-1 row-cols-md-2 row-cols-xl-4 g-3">
        <div className="col">
          <DonutPanel title="Sync Overview" segments={[
            { label: 'Syncing', value: syncing, color: '#6366f1' },
            { label: 'Online', value: Math.max(online - syncing, 0), color: '#15a34a' },
            { label: 'Offline', value: offline, color: '#f59e0b' },
          ]} />
        </div>
        <div className="col">
          <DonutPanel title="Agent Connection" segments={[
            { label: 'Online', value: online, color: '#15a34a' },
            { label: 'Offline', value: offline, color: '#dc2626' },
          ]} />
        </div>
        <div className="col">
          <SxCard className="h-100">
            <SxCardHead title="Recent Activity" icon="bi-clock-history" />
            <SxCardBody>
              {history.length === 0 ? <p className="sx-dim small mb-0">No activity yet.</p> : (
                <ul className="sx-log">
                  {history.slice(0, 6).map((row) => (
                    <li key={row.sync_id} className="sx-log__row">
                      <span className={`sx-sdot sx-sdot--${(row.status ?? '').toLowerCase()}`} />
                      <span className="sx-log__msg">{row.store_name ?? row.store_code ?? 'Store'} — {row.status?.toLowerCase()}</span>
                      <span className="sx-log__time">{timeOnly(row.started_at)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </SxCardBody>
          </SxCard>
        </div>
        <div className="col">
          <SxCard className="h-100">
            <SxCardHead title="Sync Health" icon="bi-heart-pulse" />
            <SxCardBody>
              <div className="sx-meters">
                <div className="sx-meter"><div className="sx-meter__value" style={{ color: 'var(--sx-success)' }}>{successRate}%</div><div className="sx-meter__label">Success Rate</div></div>
                <div className="sx-meter"><div className="sx-meter__value" style={{ color: 'var(--sx-accent)' }}>{avgSpeed.toLocaleString()}</div><div className="sx-meter__label">Avg Speed</div></div>
                <div className="sx-meter"><div className="sx-meter__value" style={{ color: 'var(--sx-violet)' }}>{(totalRecords / 1_000_000).toFixed(2)}M</div><div className="sx-meter__label">Rows Today</div></div>
                <div className="sx-meter"><div className="sx-meter__value" style={{ color: failure ? 'var(--sx-danger)' : 'var(--sx-faint)' }}>{failure}</div><div className="sx-meter__label">Failures</div></div>
              </div>
            </SxCardBody>
          </SxCard>
        </div>
      </div>

      {/* Bottom summary */}
      <div className="row row-cols-1 row-cols-md-3 g-3">
        <div className="col">
          <SxCard className="h-100">
            <SxCardHead title="Connection Summary" icon="bi-diagram-2" />
            <SxCardBody>
              <SxLegend segments={connCounts.map((c, i) => ({ label: c.type, value: c.count, color: ['#6366f1', '#0ea5e9', '#0d9488'][i] }))} />
            </SxCardBody>
          </SxCard>
        </div>
        <div className="col">
          <SxCard className="h-100">
            <SxCardHead title="Sync Type Distribution" icon="bi-pie-chart" />
            <SxCardBody>
              <SxLegend segments={[
                { label: 'Upsert (Master)', value: upsertSyncs, color: '#0d9488' },
                { label: 'Rolling Window', value: rollingSyncs, color: '#7c3aed' },
                { label: 'Not Syncing', value: notSyncing, color: '#cbd5e1' },
              ]} />
            </SxCardBody>
          </SxCard>
        </div>
        <div className="col">
          <SxCard className="h-100">
            <SxCardHead title="Schedules" icon="bi-calendar-event" sub={`${upcoming.length} enabled`} />
            <SxCardBody>
              {upcoming.length === 0 ? <p className="sx-dim small mb-0">No schedules configured.</p> : (
                <ul className="sx-log">
                  {upcoming.slice(0, 6).map((s) => (
                    <li key={s.schedule_id} className="sx-log__row">
                      <i className="bi bi-calendar-event" style={{ color: 'var(--sx-warning)' }} aria-hidden="true" />
                      <span className="sx-log__msg">{s.schedule_name}</span>
                      <span className="sx-log__time">{formatDateTime(s.start_time)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </SxCardBody>
          </SxCard>
        </div>
      </div>
    </div>
  )
}
