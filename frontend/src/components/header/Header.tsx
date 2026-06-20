import { useState } from 'react'
import { ThemeToggle } from '../common/ThemeToggle'
import { useAuth } from '../../hooks/useAuth'
import { APP_NAME } from '../../utils/appInfo'

interface HeaderProps {
  onToggleNav: () => void
}

export function Header({ onToggleNav }: HeaderProps) {
  const { user, logout } = useAuth()
  const [menuOpen, setMenuOpen] = useState(false)

  return (
    <header className="app-header">
      <div className="app-header__start">
        <button
          type="button"
          className="btn btn-link app-header__icon-btn app-header__nav-toggle d-md-none"
          onClick={onToggleNav}
          aria-label="Toggle navigation"
        >
          <i className="bi bi-list" aria-hidden="true" />
        </button>
        <span className="app-brand">
          <span className="app-brand__mark">
            <i className="bi bi-hexagon-fill" aria-hidden="true" />
          </span>
          <span className="app-brand__text">
            <span className="app-brand__name">{APP_NAME}</span>
            <span className="app-brand__tag">Platform</span>
          </span>
        </span>
      </div>

      <div className="app-header__actions">
        <ThemeToggle />
        <button
          type="button"
          className="btn btn-link app-header__icon-btn"
          aria-label="Notifications"
        >
          <i className="bi bi-bell" aria-hidden="true" />
        </button>

        <span className="app-header__divider" aria-hidden="true" />

        <div className="dropdown">
          <button
            type="button"
            className="btn btn-link app-header__icon-btn"
            onClick={() => setMenuOpen((open) => !open)}
            aria-label="User menu"
            aria-expanded={menuOpen}
          >
            <i className="bi bi-person-circle" aria-hidden="true" />
          </button>
          {menuOpen && (
            <>
              <div className="app-menu-backdrop" onClick={() => setMenuOpen(false)} />
              <ul className="dropdown-menu dropdown-menu-end show app-header__user-menu">
                <li>
                  <span className="dropdown-item-text small text-secondary">
                    {user?.fullName ?? 'Not signed in'}
                  </span>
                </li>
                <li>
                  <hr className="dropdown-divider" />
                </li>
                <li>
                  <button
                    type="button"
                    className="dropdown-item"
                    onClick={() => {
                      setMenuOpen(false)
                      logout()
                    }}
                  >
                    <i className="bi bi-box-arrow-right me-2" aria-hidden="true" />
                    Logout
                  </button>
                </li>
              </ul>
            </>
          )}
        </div>
      </div>
    </header>
  )
}
