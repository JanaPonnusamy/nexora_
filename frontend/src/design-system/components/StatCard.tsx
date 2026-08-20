import type { ReactNode } from 'react'

type StatTone = 'primary' | 'success' | 'warning' | 'danger' | 'neutral'

interface StatCardProps {
  label: string
  value: ReactNode
  icon?: string
  tone?: StatTone
  sub?: ReactNode
  loading?: boolean
}

export function StatCard({
  label,
  value,
  icon,
  tone = 'neutral',
  sub,
  loading = false,
}: StatCardProps) {
  return (
    <article className={`ds-stat-card ds-stat-card--${tone}${loading ? ' is-loading' : ''}`}>
      <div className="ds-stat-card__head">
        <span className="ds-stat-card__label">{label}</span>
        {icon && (
          <span className="ds-stat-card__icon" aria-hidden="true">
            <i className={`bi ${icon}`} />
          </span>
        )}
      </div>
      <div className="ds-stat-card__value">{loading ? 'Loading...' : value}</div>
      {sub != null && <div className="ds-stat-card__sub">{sub}</div>}
    </article>
  )
}

export function KpiBar({ children }: { children: ReactNode }) {
  return <div className="ds-kpi-bar">{children}</div>
}
