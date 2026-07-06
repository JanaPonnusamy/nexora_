import { useAsyncData } from '../../hooks/useAsyncData'
import { syncService } from '../../services/syncService'
import { SyncStatusBadge } from '../sync/SyncBadges'
import { Skeleton } from '../common/Skeleton'
import { ErrorState } from '../common/ErrorState'
import { formatDateTime } from '../../utils/format'

export function RecentSyncActivityCard() {
  const { data, isLoading, error, reload } = useAsyncData(syncService.history)
  const recent = (data ?? []).slice(0, 6)

  return (
    <div className="card h-100">
      <div className="card-body">
        <div className="dashboard-panel__title">Recent Sync Activity</div>
        {isLoading ? (
          <Skeleton height="7rem" />
        ) : error ? (
          <ErrorState description={error} onRetry={reload} />
        ) : recent.length === 0 ? (
          <p className="text-secondary small mb-0">No sync runs recorded yet.</p>
        ) : (
          <div className="activity-feed">
            {recent.map((row) => (
              <div className="activity-feed__item" key={row.sync_id}>
                <SyncStatusBadge status={row.status} />
                <span className="text-truncate">{row.store_name ?? row.store_code ?? 'Store'}</span>
                <span className="activity-feed__time">{formatDateTime(row.started_at)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
