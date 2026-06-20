import { usePlatformOverview } from '../../hooks/usePlatformOverview'
import { EmptyState } from '../common/EmptyState'
import { KpiCard } from './KpiCard'
import { KpiCardSkeleton } from './KpiCardSkeleton'
import { KPI_DEFINITIONS } from './overviewConfig'

export function KpiSection() {
  const { metrics, isLoading } = usePlatformOverview()

  return (
    <section className="overview-section">
      <h2 className="overview-section__title">Overview</h2>

      {isLoading ? (
        <div className="row row-cols-2 row-cols-md-3 row-cols-xl-5 g-3">
          {KPI_DEFINITIONS.map((definition) => (
            <div className="col" key={definition.key}>
              <KpiCardSkeleton />
            </div>
          ))}
        </div>
      ) : metrics.length === 0 ? (
        <EmptyState
          icon="bi-bar-chart"
          title="No metrics yet"
          description="Platform metrics will appear here once data is available."
        />
      ) : (
        <div className="row row-cols-2 row-cols-md-3 row-cols-xl-5 g-3">
          {metrics.map((metric) => (
            <div className="col" key={metric.key}>
              <KpiCard metric={metric} />
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
