import { PageHeader } from '../components/common/PageHeader'
import { EmptyState } from '../components/common/EmptyState'

export default function SettingsPage() {
  return (
    <div className="container-fluid px-0">
      <PageHeader title="Settings" breadcrumb={['Settings']} />
      <EmptyState
        icon="bi-gear"
        title="Settings coming soon"
        description="Platform settings arrive in a later phase. Configuration options will be available here."
      />
    </div>
  )
}
