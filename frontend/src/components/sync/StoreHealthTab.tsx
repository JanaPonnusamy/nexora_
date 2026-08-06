import { useAsyncData } from '../../hooks/useAsyncData'
import { syncService } from '../../services/syncService'
import { EmptyState } from '../common/EmptyState'
import { ErrorState } from '../common/ErrorState'
import { TableSkeleton } from '../common/TableSkeleton'
import { AgentBadge, ConnectionType } from './SyncBadges'
import { formatDateTime } from '../../utils/format'
import { SxCard, SxCardHead, SxCardBody, SxStat, SxChip, SxTable } from './ui'

// Architecture: Heartbeat = Agent Health only (it never reads the store DB).
// Sync = Business Data (store DB is read-only, connected only during sync).
// So the Business Activity metrics below cannot be populated until the sync
// runtime exists; they are shown as "Runtime Not Available Yet", never faked.
const BUSINESS_ACTIVITY = ['Last GRN', 'Last Purchase', 'Last Sale', 'Last Return', 'Last Stock Transfer']

export function StoreHealthTab() {
  const { data, isLoading, error, reload } = useAsyncData(syncService.storeHealth)

  if (isLoading) return <TableSkeleton rows={5} columns={6} />
  if (error || !data) return <ErrorState description={error ?? 'Failed to load store health'} onRetry={reload} />

  const online = data.filter((store) => store.agent_status === 'Online').length
  const offline = data.length - online
  const pending = data.reduce((sum, store) => sum + (store.pending_queue ?? 0), 0)

  return (
    <div className="sx-stack">
      <div className="row row-cols-2 row-cols-md-4 g-2">
        <div className="col"><SxStat icon="bi-shop" tone="indigo" value={data.length} label="Stores" /></div>
        <div className="col"><SxStat icon="bi-reception-4" tone="success" value={online} label="Online" /></div>
        <div className="col"><SxStat icon="bi-reception-0" tone="muted" value={offline} label="Offline" /></div>
        <div className="col"><SxStat icon="bi-hourglass-split" tone="warning" value={pending} label="Pending Queue" /></div>
      </div>

      <SxCard className="sx-pane">
        <SxCardHead title="Agent Health" icon="bi-heart-pulse" sub={`${data.length} stores`} />
        <SxCardBody flush>
          {data.length === 0 ? (
            <EmptyState icon="bi-heart-pulse" title="No stores" description="Active stores will appear here." />
          ) : (
            <SxTable>
              <thead>
                <tr>
                  <th>Store</th><th>Connection</th><th>Agent</th>
                  <th>Last Heartbeat</th><th>Last Sync</th><th className="sx-num">Pending</th>
                </tr>
              </thead>
              <tbody>
                {data.map((store) => (
                  <tr key={store.store_id}>
                    <td><div className="sx-rowlabel"><span className="sx-rowlabel__main">{store.store_code}</span><span className="sx-rowlabel__sub">{store.store_name}</span></div></td>
                    <td><ConnectionType value={store.connection_type} /></td>
                    <td><AgentBadge status={store.agent_status} /></td>
                    <td className="sx-dim" style={{ fontSize: '0.82rem' }}>{formatDateTime(store.last_heartbeat)}</td>
                    <td className="sx-dim" style={{ fontSize: '0.82rem' }}>{formatDateTime(store.last_sync)}</td>
                    <td className="sx-num">{store.pending_queue ? <SxChip tone="warning">{store.pending_queue}</SxChip> : <span className="sx-dim">0</span>}</td>
                  </tr>
                ))}
              </tbody>
            </SxTable>
          )}
        </SxCardBody>
      </SxCard>

      <SxCard className="sx-pane">
        <SxCardHead title="Business Activity" icon="bi-graph-up" />
        <SxCardBody>
          <p className="sx-dim small mb-3">
            <i className="bi bi-info-circle me-1" aria-hidden="true" />
            Heartbeat reports agent health only and never reads the store database. These
            metrics require the sync runtime and are not available yet.
          </p>
          <div className="row row-cols-2 row-cols-md-3 row-cols-xl-5 g-2">
            {BUSINESS_ACTIVITY.map((label) => (
              <div className="col" key={label}>
                <div className="sx-meter">
                  <div className="sx-meter__label">{label}</div>
                  <div className="sx-meter__value" style={{ fontSize: '0.9rem', color: 'var(--sx-faint)', fontWeight: 600 }}>Runtime N/A</div>
                </div>
              </div>
            ))}
          </div>
        </SxCardBody>
      </SxCard>
    </div>
  )
}
