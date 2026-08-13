import { useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { Brand } from '../brand/Brand'
import { CommandSearch } from './CommandSearch'
import { ThemeToggle } from '../common/ThemeToggle'
import { findDestination } from '../sidebar/navLookup'
import { useAuth } from '../../hooks/useAuth'
import { useAccess } from '../../hooks/useAccess'

interface HeaderProps {
  onToggleNav: () => void
}

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('')
}

export function Header({ onToggleNav }: HeaderProps) {
  const { user, logout } = useAuth()
  const { roles, currentRole, currentRoleId, setRoleId } = useAccess()
  const { pathname } = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  // No login is wired yet, so fall back to the active role as the identity.
  const displayName = user?.fullName ?? currentRole?.role_name ?? 'Administrator'
  const destination = findDestination(pathname)

  // Navigating dismisses the menu. Adjusted during render rather than in an
  // effect so the menu never paints once more on the new route.
  const [lastPath, setLastPath] = useState(pathname)
  if (lastPath !== pathname) {
    setLastPath(pathname)
    if (menuOpen) setMenuOpen(false)
  }

  useEffect(() => {
    if (!menuOpen) return
    const onDown = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) setMenuOpen(false)
    }
    const onEsc = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setMenuOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onEsc)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onEsc)
    }
  }, [menuOpen])

  return (
    <header className="app-header">
      {/* ── Zone 1: identity ─────────────────────────────────── */}
      <div className="app-header__zone app-header__zone--start">
        <button
          type="button"
          className="app-iconbtn d-md-none"
          onClick={onToggleNav}
          aria-label="Toggle navigation"
        >
          <i className="bi bi-list" aria-hidden="true" />
        </button>
        <Brand to="/" />
      </div>

      {/* ── Zone 2: where you are ────────────────────────────── */}
      <div className="app-header__zone app-header__zone--context">
        {destination && (
          <nav className="app-context" aria-label="Breadcrumb">
            {destination.group && (
              <>
                <span className="app-context__group">{destination.group}</span>
                <i className="bi bi-chevron-right app-context__sep" aria-hidden="true" />
              </>
            )}
            <span className="app-context__page" aria-current="page">
              {destination.label}
            </span>
          </nav>
        )}
      </div>

      {/* ── Zone 3: controls ─────────────────────────────────── */}
      <div className="app-header__zone app-header__zone--end">
        <CommandSearch />

        {roles.length > 0 && (
          <label className="app-rolepick">
            <span className="visually-hidden">Active role</span>
            <i className="bi bi-person-badge" aria-hidden="true" />
            <select
              className="app-rolepick__select"
              title="Active role"
              value={currentRoleId ?? ''}
              onChange={(event) => setRoleId(event.target.value || null)}
            >
              <option value="">All access</option>
              {roles.map((role) => (
                <option key={role.role_id} value={role.role_id}>
                  {role.role_name}
                </option>
              ))}
            </select>
          </label>
        )}

        <ThemeToggle />

        <button type="button" className="app-iconbtn" aria-label="Notifications">
          <i className="bi bi-bell" aria-hidden="true" />
        </button>

        <span className="app-header__rule" aria-hidden="true" />

        <div className="app-usermenu" ref={menuRef}>
          <button
            type="button"
            className="app-usermenu__trigger"
            onClick={() => setMenuOpen((open) => !open)}
            aria-label="User menu"
            aria-haspopup="menu"
            aria-expanded={menuOpen}
          >
            <span className="app-usermenu__avatar" aria-hidden="true">
              {initials(displayName)}
            </span>
            <span className="app-usermenu__name">{displayName}</span>
            <i className="bi bi-chevron-down app-usermenu__caret" aria-hidden="true" />
          </button>

          {menuOpen && (
            <div className="app-usermenu__panel" role="menu">
              <div className="app-usermenu__identity">
                <span className="app-usermenu__identity-name">{displayName}</span>
                {user?.tenant && (
                  <span className="app-usermenu__identity-meta">{user.tenant}</span>
                )}
              </div>
              <button type="button" className="app-usermenu__action" role="menuitem" onClick={logout}>
                <i className="bi bi-box-arrow-right" aria-hidden="true" />
                Sign out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  )
}
