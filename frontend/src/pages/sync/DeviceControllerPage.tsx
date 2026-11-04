import { PageHeader } from '../../components/common/PageHeader'
import { EmptyState } from '../../components/common/EmptyState'
import { DeviceController } from '../../components/sync/DeviceController'
import { WorkspaceShell } from '../../design-system/components/WorkspaceShell'
import { useAuth } from '../../hooks/useAuth'
import { isSuperAdmin } from '../label-export/labelExportAccess'
import '../../components/sync/sync-ui.css'

export default function DeviceControllerPage() {
  const { user } = useAuth()
  return (
    <WorkspaceShell
      fullWidth
      className="sx sx--compact sx-shell"
      header={
        <PageHeader
          title="Device Control"
          breadcrumb={['Operations', 'Sync', 'Device Control']}
          description="Start, stop, pause, restart and update every Nexora app on every PC through its Device Controller."
        />
      }
    >
      {isSuperAdmin(user)
        ? <DeviceController />
        : <EmptyState icon="bi-shield-lock" title="Super admin only" description="Device Control can only be used by a super admin." />}
    </WorkspaceShell>
  )
}
