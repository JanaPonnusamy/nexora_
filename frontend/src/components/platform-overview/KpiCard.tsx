import type { KpiMetric } from '../../types/platform'

export function KpiCard({ metric }: { metric: KpiMetric }) {
  return (
    <div className="card kpi-card h-100">
      <div className="card-body">
        <div className="kpi-card__header">
          <span className="kpi-card__label">{metric.label}</span>
          <span className="kpi-card__icon">
            <i className={`bi ${metric.icon}`} aria-hidden="true" />
          </span>
        </div>
        <div className="kpi-card__value">{metric.value ?? '—'}</div>
      </div>
    </div>
  )
}
