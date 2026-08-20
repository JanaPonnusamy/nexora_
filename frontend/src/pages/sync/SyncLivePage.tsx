import { PageHeader } from '../../components/common/PageHeader'
import { LiveOperationsTab } from '../../components/sync/LiveOperationsTab'
import { WorkspaceShell } from '../../design-system/components/WorkspaceShell'
import '../../components/sync/sync-ui.css'

export default function SyncLivePage() {
  return (
    <WorkspaceShell
      fullWidth
      className="sx sx--compact sx-shell"
      header={
        <PageHeader
          title="Sync Live"
          breadcrumb={['Operations', 'Sync', 'Live']}
          description="Real-time view of active sync operations across all stores."
        />
      }
    >
      <LiveOperationsTab />
    </WorkspaceShell>
  )
}
