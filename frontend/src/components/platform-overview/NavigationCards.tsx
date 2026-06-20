import { Link } from 'react-router-dom'
import { NAVIGATION_CARDS } from './overviewConfig'

export function NavigationCards() {
  return (
    <section className="overview-section">
      <h2 className="overview-section__title">Explore the platform</h2>
      <div className="row row-cols-1 row-cols-sm-2 row-cols-lg-4 g-3">
        {NAVIGATION_CARDS.map((card) => (
          <div className="col" key={card.label}>
            <Link to={card.to} className="card nav-card h-100">
              <div className="card-body d-flex align-items-center gap-3">
                <span className="nav-card__icon">
                  <i className={`bi ${card.icon}`} aria-hidden="true" />
                </span>
                <span className="nav-card__body">
                  <span className="nav-card__title">{card.label}</span>
                  <span className="nav-card__desc">{card.description}</span>
                </span>
                <i className="bi bi-chevron-right nav-card__chevron ms-auto" aria-hidden="true" />
              </div>
            </Link>
          </div>
        ))}
      </div>
    </section>
  )
}
