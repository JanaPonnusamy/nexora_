import { useAsyncData } from '../../hooks/useAsyncData'
import { syncService } from '../../services/syncService'
import { EmptyState } from '../common/EmptyState'
import { ErrorState } from '../common/ErrorState'
import { TableSkeleton } from '../common/TableSkeleton'
import { SyncStatusBadge } from './SyncBadges'
import { formatDateTime } from '../../utils/format'

export function SchedulesTab() {
  const { data, isLoading, error, reload } = useAsyncData(syncService.schedules)

  if (isLoading) return <TableSkeleton rows={5} columns={5} />
  if (error || !data) return <ErrorState description={error ?? 'Failed to load schedules'} onRetry={reload} />
  if (data.length === 0) {
    return (
      <EmptyState
        icon="bi-calendar-event"
        title="No schedules yet"
        description="Sync schedules will appear here once configured."
      />
    )
  }

  return (
    <div className="table-responsive">
      <table className="table table-hover align-middle data-table">
        <thead>
          <tr>
            <th scope="col">Schedule Name</th>
            <th scope="col">Frequency</th>
            <th scope="col">Next Run</th>
            <th scope="col">Status</th>
          </tr>
        </thead>
        <tbody>
          {data.map((schedule) => (
            <tr key={schedule.schedule_id}>
              <td className="fw-medium">{schedule.schedule_name}</td>
              <td>{schedule.schedule_type ?? '—'}</td>
              <td>{formatDateTime(schedule.start_time)}</td>
              <td><SyncStatusBadge status={schedule.is_enabled ? 'Online' : 'Offline'} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
