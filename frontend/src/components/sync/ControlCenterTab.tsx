import { useAsyncData } from '../../hooks/useAsyncData'
import { syncService } from '../../services/syncService'
import { EmptyState } from '../common/EmptyState'
import { ErrorState } from '../common/ErrorState'
import { TableSkeleton } from '../common/TableSkeleton'
import { AgentBadge, ConnectionType, SyncStatusBadge } from './SyncBadges'
import { formatDateTime } from '../../utils/format'
import type { SyncKpis } from '../../types/sync'

const KPI_CONFIG: { key: keyof SyncKpis; label: string; icon: string }[] = [
  { key: 'stores_online', label: 'Stores Online', icon: 'bi-reception-4' },
  { key: 'stores_offline', label: 'Stores Offline', icon: 'bi-reception-0' },
  { key: 'sync_running', label: 'Sync Running', icon: 'bi-arrow-repeat' },
  { key: 'queued', label: 'Queued', icon: 'bi-hourglass-split' },
  { key: 'completed_today', label: 'Completed Today', icon: 'bi-check-circle' },
  { key: 'failed_today', label: 'Failed Today', icon: 'bi-x-circle' },
]

export function ControlCenterTab() {
  const { data, isLoading, error, reload } = useAsyncData(syncService.controlCenter)

  if (isLoading) return <TableSkeleton rows={6} columns={5} />
  if (error || !data) return <ErrorState description={error ?? 'Failed to load control center'} onRetry={reload} />

  return (
    <div>
      <div className="row row-cols-2 row-cols-md-3 row-cols-xl-6 g-3 mb-4">
        {KPI_CONFIG.map((kpi) => (
          <div className="col" key={kpi.key}>
            <div className="card kpi-card h-100">
              <div className="card-body">
                <div className="kpi-card__header">
                  <span className="kpi-card__label">{kpi.label}</span>
                  <span className="kpi-card__icon">
                    <i className={`bi ${kpi.icon}`} aria-hidden="true" />
                  </span>
                </div>
                <div className="kpi-card__value">{data.kpis[kpi.key]}</div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {data.stores.length === 0 ? (
        <EmptyState icon="bi-shop" title="No stores" description="Active stores will appear here." />
      ) : (
        <div className="table-responsive">
          <table className="table table-hover align-middle data-table">
            <thead>
              <tr>
                <th scope="col">Store Code</th>
                <th scope="col">Store Name</th>
                <th scope="col">Connection</th>
                <th scope="col">Agent</th>
                <th scope="col">Activity</th>
                <th scope="col">Last Sync</th>
                <th scope="col">Status</th>
              </tr>
            </thead>
            <tbody>
              {data.stores.map((store) => (
                <tr key={store.store_id}>
                  <td>{store.store_code}</td>
                  <td className="fw-medium">{store.store_name}</td>
                  <td><ConnectionType value={store.connection_type} /></td>
                  <td><AgentBadge status={store.agent_status} /></td>
                  <td>{store.current_activity}</td>
                  <td>{formatDateTime(store.last_sync)}</td>
                  <td><SyncStatusBadge status={store.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
