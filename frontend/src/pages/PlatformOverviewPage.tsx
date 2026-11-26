import { PageHeader } from '../components/common/PageHeader'
import bannerArt from '../assets/ai/dashboard-banner.webp'
import { KpiSection } from '../components/platform-overview/KpiSection'
import { QuickActions } from '../components/platform-overview/QuickActions'
import { SystemStatusCard } from '../components/platform-overview/SystemStatusCard'
import { StoreHealthSummaryCard } from '../components/platform-overview/StoreHealthSummaryCard'
import { RecentSyncActivityCard } from '../components/platform-overview/RecentSyncActivityCard'

export default function PlatformOverviewPage() {
  return (
    <div className="container-fluid px-0">
      <PageHeader title="Platform Overview" breadcrumb={['Platform Overview']} />
      <section className="overview-banner" style={{ backgroundImage: `url(${bannerArt})` }}>
        <span className="overview-banner__ai"><i className="bi bi-stars" aria-hidden="true" /> AI-Powered Workspace</span>
        <h2 className="overview-banner__title">Pharma operations, intelligently connected.</h2>
        <p className="overview-banner__sub">Inventory, procurement and supplier intelligence across every branch.</p>
      </section>
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
