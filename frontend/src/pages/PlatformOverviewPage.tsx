import { PageHeader } from '../components/common/PageHeader'
import { KpiSection } from '../components/platform-overview/KpiSection'
import { QuickActions } from '../components/platform-overview/QuickActions'
import { NavigationCards } from '../components/platform-overview/NavigationCards'

export default function PlatformOverviewPage() {
  return (
    <div className="container-fluid px-0">
      <PageHeader title="Platform Overview" breadcrumb={['Platform Overview']} />
      <KpiSection />
      <QuickActions />
      <NavigationCards />
    </div>
  )
}
