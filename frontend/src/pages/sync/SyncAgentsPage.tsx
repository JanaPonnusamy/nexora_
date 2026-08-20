import { PageHeader } from '../../components/common/PageHeader'
import { AgentOpsTab } from '../../components/sync/AgentOpsTab'
import { WorkspaceShell } from '../../design-system/components/WorkspaceShell'
import '../../components/sync/sync-ui.css'

export default function SyncAgentsPage() {
  return (
    <WorkspaceShell
      fullWidth
      className="sx sx--compact sx-shell"
      header={
        <PageHeader
          title="Sync Agents"
          breadcrumb={['Operations', 'Sync', 'Agents']}
          description="Monitor and manage sync agent operations and status."
        />
      }
    >
      <AgentOpsTab />
    </WorkspaceShell>
  )
}
