import { PageHeader } from '../../components/common/PageHeader'
import { EmptyState } from '../../components/common/EmptyState'
import { RemoteTerminal } from '../../components/sync/RemoteTerminal'
import { WorkspaceShell } from '../../design-system/components/WorkspaceShell'
import { useAuth } from '../../hooks/useAuth'
import { isSuperAdmin } from '../label-export/labelExportAccess'
import '../../components/sync/sync-ui.css'

export default function RemoteTerminalPage() {
  const { user } = useAuth()
  return (
    <WorkspaceShell
      fullWidth
      className="sx sx--compact sx-shell"
      header={
        <PageHeader
          title="Remote Terminal"
          breadcrumb={['Operations', 'Sync', 'Remote Terminal']}
          description="PowerShell on any enrolled store or HO PC. Every command and its output is recorded."
        />
      }
    >
      {isSuperAdmin(user)
        ? <RemoteTerminal />
        : <EmptyState icon="bi-shield-lock" title="Super admin only" description="The remote terminal can only be used by a super admin." />}
    </WorkspaceShell>
  )
}
