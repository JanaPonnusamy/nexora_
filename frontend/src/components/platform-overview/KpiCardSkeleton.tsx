import { Skeleton } from '../common/Skeleton'

export function KpiCardSkeleton() {
  return (
    <div className="card kpi-card h-100" aria-hidden="true">
      <div className="card-body">
        <div className="kpi-card__header">
          <Skeleton width="45%" height="0.8rem" />
          <Skeleton width="2rem" height="2rem" rounded />
        </div>
        <Skeleton width="55%" height="1.75rem" className="mt-3" />
      </div>
    </div>
  )
}
