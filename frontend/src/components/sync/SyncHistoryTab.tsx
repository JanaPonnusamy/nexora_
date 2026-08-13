import { useCallback, useEffect, useMemo, useState } from 'react'
import { syncService } from '../../services/syncService'
import { EmptyState } from '../common/EmptyState'
import { ErrorState } from '../common/ErrorState'
import { TableSkeleton } from '../common/TableSkeleton'
import { SyncStatusBadge, SyncTypeBadge } from './SyncBadges'
import { formatDateTime } from '../../utils/format'
import { SxCard, SxCardHead, SxCardBody, SxStat, SxTable, SxSearch, SxSelect, SxButton } from './ui'
import { ExecutionDrawer, formatDuration } from './ExecutionDrawer'
import { FilterBar } from '../../design-system/components/FilterBar'
import type {
  StoreHealthRow,
  SyncHistoryFilters,
  SyncHistoryRow,
  SyncStatistics,
} from '../../types/sync'

const STATUS_OPTIONS = ['RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED', 'PAUSED', 'PENDING']
const TYPE_OPTIONS = ['FULL', 'DELTA', 'INCREMENTAL']
const MODE_OPTIONS = ['FULL', 'UPSERT', 'ROLLING_WINDOW']

function num(n: number | null | undefined): string {
  return (n ?? 0).toLocaleString()
}

function exportCsv(rows: SyncHistoryRow[]) {
  const cols: [string, (r: SyncHistoryRow) => string | number][] = [
    ['Execution ID', (r) => r.execution_id],
    ['Started At', (r) => r.started_at ?? ''],
    ['Completed At', (r) => r.completed_at ?? ''],
    ['Duration (s)', (r) => r.duration_seconds ?? ''],
    ['Store', (r) => r.store_name ?? r.store_code ?? ''],
    ['Agent Version', (r) => r.agent_version ?? ''],
    ['Sync Mode', (r) => r.sync_mode ?? ''],
    ['Execution Type', (r) => r.execution_type ?? ''],
    ['Status', (r) => r.status ?? ''],
    ['Tables', (r) => r.table_count],
    ['Records Read', (r) => r.rows_read],
    ['Records Inserted', (r) => r.rows_inserted],
    ['Records Updated', (r) => r.rows_updated],
    ['Errors', (r) => r.error_count],
    ['Retries', (r) => r.retry_count],
  ]
  const esc = (v: string | number) => `"${String(v).replace(/"/g, '""')}"`
  const csv = [
    cols.map(([h]) => esc(h)).join(','),
    ...rows.map((r) => cols.map(([, f]) => esc(f(r))).join(',')),
  ].join('\r\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `sync-history-${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

export function SyncHistoryTab() {
  const [filters, setFilters] = useState<SyncHistoryFilters>({})
  const [search, setSearch] = useState('')
  const [data, setData] = useState<SyncHistoryRow[] | null>(null)
  const [stats, setStats] = useState<SyncStatistics | null>(null)
  const [stores, setStores] = useState<StoreHealthRow[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<SyncHistoryRow | null>(null)

  const load = useCallback(async (f: SyncHistoryFilters) => {
    setIsLoading(true)
    setError(null)
    try {
      const [rows, statistics] = await Promise.all([
        syncService.history(f),
        syncService.historyStatistics(),
      ])
      setData(rows)
      setStats(statistics)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load sync history')
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => { void load(filters) }, [load, filters])
  useEffect(() => { syncService.storeHealth().then(setStores).catch(() => {}) }, [])

  const applySearch = () => setFilters((f) => ({ ...f, search: search.trim() || undefined }))
  const setFilter = (key: keyof SyncHistoryFilters, value: string) =>
    setFilters((f) => ({ ...f, [key]: value || undefined }))
  const hasFilters = Object.values(filters).some(Boolean)

  const durationCards = useMemo(() => {
    if (!stats) return '—'
    return formatDuration(stats.avg_duration_seconds)
  }, [stats])

  if (isLoading && !data) return <TableSkeleton rows={8} columns={8} />
  if (error && !data) return <ErrorState description={error} onRetry={() => load(filters)} />

  return (
    <div className="sx-stack">
      {/* ---- Performance summary cards ---- */}
      <div className="row row-cols-2 row-cols-md-4 g-2">
        <div className="col"><SxStat icon="bi-collection" tone="indigo" value={num(stats?.total_executions)} label="Total Executions" /></div>
        <div className="col"><SxStat icon="bi-check-circle" tone="success" value={num(stats?.successful)} label="Successful" sub={stats ? `${stats.success_rate}% success` : undefined} /></div>
        <div className="col"><SxStat icon="bi-x-circle" tone="danger" value={num(stats?.failed)} label="Failed" /></div>
        <div className="col"><SxStat icon="bi-stopwatch" tone="teal" value={durationCards} label="Avg Duration" /></div>
        <div className="col"><SxStat icon="bi-cloud-upload" tone="info" value={num(stats?.rows_uploaded_today)} label="Rows Uploaded Today" /></div>
        <div className="col"><SxStat icon="bi-database-up" tone="violet" value={num(stats?.largest_sync_rows)} label="Largest Sync (rows)" /></div>
        <div className="col"><SxStat icon="bi-hourglass-split" tone="warning" value={stats?.slowest_table ?? '—'} label="Slowest Table" sub={stats?.slowest_table_seconds != null ? formatDuration(stats.slowest_table_seconds) : undefined} /></div>
        <div className="col"><SxStat icon="bi-broadcast" tone="indigo" value={num(stats?.running)} label="Running Now" /></div>
      </div>

      {/* ---- Filter bar ---- */}
      <SxCard className="sx-pane">
        <SxCardBody>
          <FilterBar compact ariaLabel="Sync history filters">
            <SxSearch value={search} onChange={setSearch} placeholder="Search Execution ID…" ariaLabel="Search execution id" />
            <SxButton icon="bi-search" variant="ghost" sm onClick={applySearch}>Search</SxButton>
            <SxSelect value={filters.store_id ?? ''} onChange={(v) => setFilter('store_id', v)} ariaLabel="Filter by store">
              <option value="">All Stores</option>
              {stores.map((s) => <option key={s.store_id} value={s.store_id}>{s.store_name ?? s.store_code}</option>)}
            </SxSelect>
            <SxSelect value={filters.status ?? ''} onChange={(v) => setFilter('status', v)} ariaLabel="Filter by status">
              <option value="">All Statuses</option>
              {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
            </SxSelect>
            <SxSelect value={filters.execution_type ?? ''} onChange={(v) => setFilter('execution_type', v)} ariaLabel="Filter by execution type">
              <option value="">All Types</option>
              {TYPE_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
            </SxSelect>
            <SxSelect value={filters.sync_mode ?? ''} onChange={(v) => setFilter('sync_mode', v)} ariaLabel="Filter by sync mode">
              <option value="">All Modes</option>
              {MODE_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
            </SxSelect>
            {hasFilters && (
              <SxButton icon="bi-x-circle" variant="ghost" sm onClick={() => { setSearch(''); setFilters({}) }}>Clear</SxButton>
            )}
            <div className="ms-auto d-flex gap-2">
              <SxButton icon="bi-arrow-clockwise" variant="ghost" sm onClick={() => load(filters)}>Refresh</SxButton>
              <SxButton icon="bi-filetype-csv" variant="primary" sm disabled={!data || data.length === 0} onClick={() => data && exportCsv(data)}>Export CSV</SxButton>
            </div>
          </FilterBar>
        </SxCardBody>
      </SxCard>

      {/* ---- Execution grid ---- */}
      {!data || data.length === 0 ? (
        <EmptyState icon="bi-clock-history" title="No sync history yet"
          description={hasFilters ? 'No executions match the current filters.' : 'Completed, running and failed sync runs will appear here.'} />
      ) : (
        <SxCard className="sx-pane">
          <SxCardHead title="Execution History" icon="bi-clock-history" sub={`${data.length} executions`} />
          <SxCardBody flush>
            <SxTable>
              <thead>
                <tr>
                  <th>Execution</th><th>Store</th><th>Type</th><th>Mode</th>
                  <th>Started</th><th>Duration</th>
                  <th className="sx-num">Tables</th><th className="sx-num">Read</th>
                  <th className="sx-num">Ins</th><th className="sx-num">Upd</th>
                  <th className="sx-num">Errors</th><th>Status</th>
                </tr>
              </thead>
              <tbody>
                {data.map((row) => (
                  <tr key={row.execution_id} className="sx-clickrow" onClick={() => setSelected(row)}>
                    <td className="sx-dim" title={row.execution_id} style={{ fontFamily: 'monospace', fontSize: '0.78rem' }}>
                      {row.execution_id.slice(0, 8)}…
                    </td>
                    <td className="sx-strong">{row.store_name ?? row.store_code ?? '—'}</td>
                    <td className="sx-dim">{row.execution_type ?? '—'}</td>
                    <td><SyncTypeBadge value={row.sync_mode} /></td>
                    <td className="sx-dim" style={{ fontSize: '0.82rem' }}>{formatDateTime(row.started_at)}</td>
                    <td>{formatDuration(row.duration_seconds)}</td>
                    <td className="sx-num">{num(row.table_count)}</td>
                    <td className="sx-num">{num(row.rows_read)}</td>
                    <td className="sx-num">{num(row.rows_inserted)}</td>
                    <td className="sx-num">{num(row.rows_updated)}</td>
                    <td className="sx-num">
                      {row.error_count > 0 ? <span className="sx-err-count">{row.error_count}</span> : <span className="sx-dim">0</span>}
                    </td>
                    <td><SyncStatusBadge status={row.status} /></td>
                  </tr>
                ))}
              </tbody>
            </SxTable>
          </SxCardBody>
        </SxCard>
      )}

      {selected && <ExecutionDrawer row={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}
