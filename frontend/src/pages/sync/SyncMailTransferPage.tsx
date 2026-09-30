import { PageHeader } from '../../components/common/PageHeader'
import { MailTransferTab } from '../../components/sync/MailTransferTab'
import { WorkspaceShell } from '../../design-system/components/WorkspaceShell'
import '../../components/sync/sync-ui.css'

export default function SyncMailTransferPage() {
  return (
    <WorkspaceShell
      fullWidth
      className="sx sx--compact sx-shell"
      header={
        <PageHeader
          title="Mail Transfer"
          breadcrumb={['Operations', 'Sync', 'Mail Transfer']}
          description="EMAIL FILE_TRANSFER status, mail configuration, and recent packages for stores with no LAN/domain/static-IP route to HO."
        />
      }
    >
      <MailTransferTab />
    </WorkspaceShell>
  )
}
