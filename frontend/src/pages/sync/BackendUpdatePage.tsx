import { PageHeader } from '../../components/common/PageHeader'
import { BackendUpdatePanel } from '../../components/sync/BackendUpdatePanel'
import { WorkspaceShell } from '../../design-system/components/WorkspaceShell'
import '../../components/sync/sync-ui.css'

export default function BackendUpdatePage() {
  return (
    <WorkspaceShell
      fullWidth
      className="sx sx--compact sx-shell"
      header={
        <PageHeader
          title="Backend Update"
          breadcrumb={['Operations', 'Sync', 'Backend Update']}
          description="Remotely pull main, reinstall, and restart each HO backend node."
        />
      }
    >
      <BackendUpdatePanel />
    </WorkspaceShell>
  )
}
