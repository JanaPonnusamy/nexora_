import { useAsyncData } from '../../hooks/useAsyncData'
import { syncService } from '../../services/syncService'
import { EmptyState } from '../common/EmptyState'
import { ErrorState } from '../common/ErrorState'
import { TableSkeleton } from '../common/TableSkeleton'
import { SyncStatusBadge } from './SyncBadges'
import { formatDateTime } from '../../utils/format'

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
  if (data.length === 0) {
    return (
      <EmptyState
        icon="bi-clock-history"
        title="No sync history yet"
        description="Completed and failed sync runs will appear here."
      />
    )
  }

  return (
    <div className="table-responsive">
      <table className="table table-hover align-middle data-table">
        <thead>
          <tr>
            <th scope="col">Execution Id</th>
            <th scope="col">Store</th>
            <th scope="col">Scope</th>
            <th scope="col">Started</th>
            <th scope="col">Completed</th>
            <th scope="col">Duration</th>
            <th scope="col">Rows</th>
            <th scope="col">Status</th>
          </tr>
        </thead>
        <tbody>
          {data.map((row) => (
            <tr key={row.sync_id}>
              <td>{row.sync_id}</td>
              <td className="fw-medium">{row.store_name ?? row.store_code ?? '—'}</td>
              <td>{row.scope ?? '—'}</td>
              <td>{formatDateTime(row.started_at)}</td>
              <td>{formatDateTime(row.completed_at)}</td>
              <td>{formatDuration(row.duration_seconds)}</td>
              <td>{row.rows}</td>
              <td><SyncStatusBadge status={row.status} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
