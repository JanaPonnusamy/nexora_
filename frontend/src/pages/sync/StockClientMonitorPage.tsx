import { PageHeader } from '../../components/common/PageHeader'
import { StockClientMonitor } from '../../components/sync/StockClientMonitor'
import { WorkspaceShell } from '../../design-system/components/WorkspaceShell'
import '../../components/sync/sync-ui.css'

export default function StockClientMonitorPage() {
  return (
    <WorkspaceShell
      fullWidth
      className="sx sx--compact sx-shell"
      header={
        <PageHeader
          title="Store Client Monitor"
          breadcrumb={['Operations', 'Sync', 'Store Clients']}
          description="Fleet status + HO-authorized, per-store updates for the desktop Stock Client."
        />
      }
    >
      <StockClientMonitor />
    </WorkspaceShell>
  )
}
