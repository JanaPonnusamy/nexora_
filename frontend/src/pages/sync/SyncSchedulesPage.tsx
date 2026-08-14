import { PageHeader } from '../../components/common/PageHeader'
import { SchedulesTab } from '../../components/sync/SchedulesTab'
import { WorkspaceShell } from '../../design-system/components/WorkspaceShell'
import '../../components/sync/sync-ui.css'

export default function SyncSchedulesPage() {
  return (
    <WorkspaceShell
      fullWidth
      className="sx sx--compact sx-shell"
      header={
        <PageHeader
          title="Sync Schedules"
          breadcrumb={['Operations', 'Sync', 'Schedules']}
          description="Manage and monitor scheduled sync jobs across stores."
        />
      }
    >
      <SchedulesTab />
    </WorkspaceShell>
  )
}
