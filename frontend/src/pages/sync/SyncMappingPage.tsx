import { PageHeader } from '../../components/common/PageHeader'
import { ColumnMappingTab } from '../../components/sync/ColumnMappingTab'
import { WorkspaceShell } from '../../design-system/components/WorkspaceShell'
import '../../components/sync/sync-ui.css'

export default function SyncMappingPage() {
  return (
    <WorkspaceShell
      fullWidth
      className="sx sx--compact sx-shell"
      header={
        <PageHeader
          title="Sync Mapping"
          breadcrumb={['Operations', 'Sync', 'Mapping']}
          description="Manage column mappings between source and destination tables."
        />
      }
    >
      <ColumnMappingTab />
    </WorkspaceShell>
  )
}
