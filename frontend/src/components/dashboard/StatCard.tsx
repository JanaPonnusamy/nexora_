import type { ReactNode } from 'react'

interface StatCardProps {
  label: string
  value: ReactNode
  icon?: string
  tone?: string
}

export function StatCard({ label, value, icon, tone = 'primary' }: StatCardProps) {
  return (
    <div className="card stat-card h-100">
      <div className="card-body">
        <div className="stat-card__row">
          <span className="stat-card__label">{label}</span>
          {icon && (
            <span className={`stat-card__icon text-bg-${tone}`}>
              <i className={`bi ${icon}`} aria-hidden="true" />
            </span>
          )}
        </div>
        <div className="stat-card__value">{value}</div>
      </div>
    </div>
  )
}
