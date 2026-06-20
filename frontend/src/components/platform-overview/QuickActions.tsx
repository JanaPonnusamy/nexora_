import { Link } from 'react-router-dom'
import { QUICK_ACTIONS } from './overviewConfig'

export function QuickActions() {
  return (
    <section className="overview-section">
      <h2 className="overview-section__title">Quick Actions</h2>
      <div className="row row-cols-1 row-cols-sm-2 row-cols-xl-5 g-3">
        {QUICK_ACTIONS.map((action) => (
          <div className="col" key={action.label}>
            <Link to={action.to} className="card quick-action h-100">
              <div className="card-body">
                <span className="quick-action__icon">
                  <i className={`bi ${action.icon}`} aria-hidden="true" />
                </span>
                <span className="quick-action__label">{action.label}</span>
                <span className="quick-action__desc">{action.description}</span>
              </div>
            </Link>
          </div>
        ))}
      </div>
    </section>
  )
}
