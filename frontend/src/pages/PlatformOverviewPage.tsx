import { PageHeader } from '../components/common/PageHeader'
import { KpiSection } from '../components/platform-overview/KpiSection'
import { QuickActions } from '../components/platform-overview/QuickActions'
import { SystemStatusCard } from '../components/platform-overview/SystemStatusCard'
import { StoreHealthSummaryCard } from '../components/platform-overview/StoreHealthSummaryCard'
import { RecentSyncActivityCard } from '../components/platform-overview/RecentSyncActivityCard'

export default function PlatformOverviewPage() {
  return (
    <div className="container-fluid px-0">
      <PageHeader title="Platform Overview" breadcrumb={['Platform Overview']} />
      <KpiSection />

      <section className="overview-section">
        <h2 className="overview-section__title">Operations</h2>
        <div className="row row-cols-1 row-cols-lg-3 g-3">
          <div className="col">
            <StoreHealthSummaryCard />
          </div>
          <div className="col">
            <RecentSyncActivityCard />
          </div>
          <div className="col">
            <SystemStatusCard />
          </div>
        </div>
      </section>

      <QuickActions />
    </div>
  )
}
