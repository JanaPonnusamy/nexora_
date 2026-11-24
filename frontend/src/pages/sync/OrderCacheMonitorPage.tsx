import { PageHeader } from '../../components/common/PageHeader'
import { OrderCacheMonitor } from '../../components/sync/OrderCacheMonitor'
import { WorkspaceShell } from '../../design-system/components/WorkspaceShell'
import '../../components/sync/sync-ui.css'

export default function OrderCacheMonitorPage() {
  return (
    <WorkspaceShell
      fullWidth
      className="sx sx--compact sx-shell"
      header={
        <PageHeader
          title="Order Cache Monitor"
          breadcrumb={['Operations', 'Sync', 'Order Cache']}
          description="Per-store local SQLite order cache: file age, last write-back, unsynced rows, and force pull/push/import."
        />
      }
    >
      <OrderCacheMonitor />
    </WorkspaceShell>
  )
}
