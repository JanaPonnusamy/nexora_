import { PageHeader } from '../../components/common/PageHeader'
import { StoreHealthTab } from '../../components/sync/StoreHealthTab'
import { WorkspaceShell } from '../../design-system/components/WorkspaceShell'
import '../../components/sync/sync-ui.css'

export default function SyncStoreHealthPage() {
  return (
    <WorkspaceShell
      fullWidth
      className="sx sx--compact sx-shell"
      header={
        <PageHeader
          title="Sync Store Health"
          breadcrumb={['Operations', 'Sync', 'Store Health']}
          description="Monitor store connectivity and sync health status."
        />
      }
    >
      <StoreHealthTab />
    </WorkspaceShell>
  )
}
