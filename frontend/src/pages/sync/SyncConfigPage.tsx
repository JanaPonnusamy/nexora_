import { PageHeader } from '../../components/common/PageHeader'
import { TableConfigTab } from '../../components/sync/TableConfigTab'
import { WorkspaceShell } from '../../design-system/components/WorkspaceShell'
import '../../components/sync/sync-ui.css'

export default function SyncConfigPage() {
  return (
    <WorkspaceShell
      fullWidth
      className="sx sx--compact sx-shell"
      header={
        <PageHeader
          title="Sync Config"
          breadcrumb={['Operations', 'Sync', 'Config']}
          description="Configure sync table settings and parameters."
        />
      }
    >
      <TableConfigTab />
    </WorkspaceShell>
  )
}
