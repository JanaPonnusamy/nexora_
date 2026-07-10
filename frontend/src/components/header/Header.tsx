import { useState } from 'react'
import { ThemeToggle } from '../common/ThemeToggle'
import { useAuth } from '../../hooks/useAuth'
import { useAccess } from '../../hooks/useAccess'

interface HeaderProps {
  onToggleNav: () => void
}

export function Header({ onToggleNav }: HeaderProps) {
  const { user, logout } = useAuth()
  const { roles, currentRole, currentRoleId, setRoleId } = useAccess()
  const [menuOpen, setMenuOpen] = useState(false)

  // No login is wired yet, so fall back to the active role as the identity.
  const displayName = user?.fullName ?? currentRole?.role_name ?? 'Administrator'

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
          <img src="/logo_mark.png" alt="Axythic Pharma" className="app-brand__logo" />
          <span className="app-brand__name">Axythic</span>
          <span className="app-brand__pharma-text">Pharma</span>
        </span>
      </div>

      <div className="app-header__actions">
        {roles.length > 0 && (
          <select
            className="form-select form-select-sm w-auto"
            aria-label="Active role"
            title="Active role"
            value={currentRoleId ?? ''}
            onChange={(e) => setRoleId(e.target.value || null)}
          >
            <option value="">All access</option>
            {roles.map((r) => (
              <option key={r.role_id} value={r.role_id}>{r.role_name}</option>
            ))}
          </select>
        )}
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
            className="btn btn-link app-header__icon-btn app-header__user"
            onClick={() => setMenuOpen((open) => !open)}
            aria-label="User menu"
            aria-expanded={menuOpen}
          >
            <i className="bi bi-person-circle" aria-hidden="true" />
            <span className="app-header__user-name">{displayName}</span>
          </button>
          {menuOpen && (
            <>
              <div className="app-menu-backdrop" onClick={() => setMenuOpen(false)} />
              <ul className="dropdown-menu dropdown-menu-end show app-header__user-menu">
                <li>
                  <span className="dropdown-item-text small text-secondary">
                    {displayName}
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
