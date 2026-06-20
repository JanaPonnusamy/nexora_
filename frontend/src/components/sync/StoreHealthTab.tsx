import { useAsyncData } from '../../hooks/useAsyncData'
import { syncService } from '../../services/syncService'
import { EmptyState } from '../common/EmptyState'
import { ErrorState } from '../common/ErrorState'
import { TableSkeleton } from '../common/TableSkeleton'
import { AgentBadge, ConnectionType } from './SyncBadges'
import { formatDateTime } from '../../utils/format'

// Architecture: Heartbeat = Agent Health only (it never reads the store DB).
// Sync = Business Data (store DB is read-only, connected only during sync).
// So the Business Activity metrics below cannot be populated until the sync
// runtime exists; they are shown as "Runtime Not Available Yet", never faked.
const BUSINESS_ACTIVITY = ['Last GRN', 'Last Purchase', 'Last Sale', 'Last Return', 'Last Stock Transfer']

export function StoreHealthTab() {
  const { data, isLoading, error, reload } = useAsyncData(syncService.storeHealth)

  if (isLoading) return <TableSkeleton rows={5} columns={6} />
  if (error || !data) return <ErrorState description={error ?? 'Failed to load store health'} onRetry={reload} />

  return (
    <div>
      <h2 className="overview-section__title">Sync Health</h2>
      {data.length === 0 ? (
        <EmptyState icon="bi-heart-pulse" title="No stores" description="Active stores will appear here." />
      ) : (
        <div className="table-responsive">
          <table className="table table-hover align-middle data-table">
            <thead>
              <tr>
                <th scope="col">Store Code</th>
                <th scope="col">Store Name</th>
                <th scope="col">Connection</th>
                <th scope="col">Agent</th>
                <th scope="col">Last Heartbeat</th>
                <th scope="col">Last Sync</th>
                <th scope="col">Pending Queue</th>
              </tr>
            </thead>
            <tbody>
              {data.map((store) => (
                <tr key={store.store_id}>
                  <td>{store.store_code}</td>
                  <td className="fw-medium">{store.store_name}</td>
                  <td><ConnectionType value={store.connection_type} /></td>
                  <td><AgentBadge status={store.agent_status} /></td>
                  <td>{formatDateTime(store.last_heartbeat)}</td>
                  <td>{formatDateTime(store.last_sync)}</td>
                  <td>{store.pending_queue}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h2 className="overview-section__title mt-4">Business Activity</h2>
      <div className="card">
        <div className="card-body">
          <p className="text-secondary small mb-3">
            <i className="bi bi-info-circle me-1" aria-hidden="true" />
            Heartbeat reports agent health only and never reads the store database. These
            metrics require the sync runtime and are not available yet.
          </p>
          <div className="row row-cols-2 row-cols-md-3 row-cols-xl-5 g-2">
            {BUSINESS_ACTIVITY.map((label) => (
              <div className="col" key={label}>
                <div className="border rounded p-2">
                  <div className="small text-secondary">{label}</div>
                  <div className="fw-medium">Runtime Not Available Yet</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
