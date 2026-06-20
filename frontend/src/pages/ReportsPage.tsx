import { PageHeader } from '../components/common/PageHeader'
import { EmptyState } from '../components/common/EmptyState'

export default function ReportsPage() {
  return (
    <div className="container-fluid px-0">
      <PageHeader title="Reports" breadcrumb={['Reports']} />
      <EmptyState
        icon="bi-bar-chart"
        title="No reports yet"
        description="Reporting arrives in a later phase. Platform reports will be available here."
      />
    </div>
  )
}
