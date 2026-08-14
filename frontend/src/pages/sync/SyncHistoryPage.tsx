import { PageHeader } from '../../components/common/PageHeader'
import { SyncHistoryTab } from '../../components/sync/SyncHistoryTab'
import { WorkspaceShell } from '../../design-system/components/WorkspaceShell'
import '../../components/sync/sync-ui.css'

export default function SyncHistoryPage() {
  return (
    <WorkspaceShell
      fullWidth
      className="sx sx--compact sx-shell"
      header={
        <PageHeader
          title="Sync History"
          breadcrumb={['Operations', 'Sync', 'History']}
          description="Browse historical sync execution logs and results."
        />
      }
    >
      <SyncHistoryTab />
    </WorkspaceShell>
  )
}
