import { useAsyncData } from '../../hooks/useAsyncData'
import { syncService } from '../../services/syncService'
import { EmptyState } from '../common/EmptyState'
import { ErrorState } from '../common/ErrorState'
import { TableSkeleton } from '../common/TableSkeleton'
import { SyncStatusBadge } from './SyncBadges'
import { DonutChart } from '../dashboard/DonutChart'
import { formatDateTime } from '../../utils/format'
import { SxCard, SxCardHead, SxCardBody, SxStat, SxLegend, SxTable } from './ui'

function formatDuration(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return '—'
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  return `${minutes}m ${seconds % 60}s`
}

export function SyncHistoryTab() {
  const { data, isLoading, error, reload } = useAsyncData(syncService.history)

  if (isLoading) return <TableSkeleton rows={6} columns={6} />
  if (error || !data) return <ErrorState description={error ?? 'Failed to load sync history'} onRetry={reload} />

  const success = data.filter((row) => row.status === 'COMPLETED').length
  const failure = data.filter((row) => row.status === 'FAILED').length
  const records = data.reduce((sum, row) => sum + (row.rows ?? 0), 0)
  const durations = data.map((row) => row.duration_seconds).filter((d): d is number => d != null)
  const avgDuration = durations.length ? Math.round(durations.reduce((sum, d) => sum + d, 0) / durations.length) : null

  return (
    <div className="sx-stack">
      <div className="row row-cols-2 row-cols-xl-4 g-3">
        <div className="col"><SxStat icon="bi-check-circle" tone="success" value={success} label="Success" /></div>
        <div className="col"><SxStat icon="bi-x-circle" tone="danger" value={failure} label="Failure" /></div>
        <div className="col"><SxStat icon="bi-database" tone="info" value={records.toLocaleString()} label="Records Processed" /></div>
        <div className="col"><SxStat icon="bi-stopwatch" tone="indigo" value={formatDuration(avgDuration)} label="Avg Duration" /></div>
      </div>

      {data.length === 0 ? (
        <EmptyState icon="bi-clock-history" title="No sync history yet"
          description="Completed and failed sync runs will appear here." />
      ) : (
        <div className="row g-3">
          <div className="col-12 col-xl-9">
            <SxCard>
              <SxCardHead title="Run History" icon="bi-clock-history" sub={`${data.length} runs`} />
              <SxCardBody flush>
                <SxTable>
                  <thead>
                    <tr>
                      <th>Execution</th><th>Store</th><th>Scope</th>
                      <th>Started</th><th>Completed</th><th>Duration</th>
                      <th className="sx-num">Rows</th><th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.map((row) => (
                      <tr key={row.sync_id}>
                        <td className="sx-dim">{row.sync_id}</td>
                        <td className="sx-strong">{row.store_name ?? row.store_code ?? '—'}</td>
                        <td className="sx-dim">{row.scope ?? '—'}</td>
                        <td className="sx-dim" style={{ fontSize: '0.82rem' }}>{formatDateTime(row.started_at)}</td>
                        <td className="sx-dim" style={{ fontSize: '0.82rem' }}>{formatDateTime(row.completed_at)}</td>
                        <td>{formatDuration(row.duration_seconds)}</td>
                        <td className="sx-num">{row.rows.toLocaleString()}</td>
                        <td><SyncStatusBadge status={row.status} /></td>
                      </tr>
                    ))}
                  </tbody>
                </SxTable>
              </SxCardBody>
            </SxCard>
          </div>
          <div className="col-12 col-xl-3">
            <SxCard className="h-100">
              <SxCardHead title="Success vs Failure" icon="bi-pie-chart" />
              <SxCardBody>
                <div className="sx-donut">
                  <DonutChart size={108} thickness={14} segments={[
                    { label: 'Success', value: success, color: '#15a34a' },
                    { label: 'Failure', value: failure, color: '#dc2626' },
                  ]} />
                  <SxLegend segments={[
                    { label: 'Success', value: success, color: '#15a34a' },
                    { label: 'Failure', value: failure, color: '#dc2626' },
                  ]} />
                </div>
              </SxCardBody>
            </SxCard>
          </div>
        </div>
      )}
    </div>
  )
}
