import { usePlatformOverview } from '../../hooks/usePlatformOverview'
import { ErrorState } from '../common/ErrorState'
import { KpiCard } from './KpiCard'
import { KpiCardSkeleton } from './KpiCardSkeleton'
import { KPI_DEFINITIONS } from './overviewConfig'

export function KpiSection() {
  const { metrics, isLoading, error, reload } = usePlatformOverview()

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
      ) : error ? (
        <ErrorState description={error} onRetry={reload} />
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
