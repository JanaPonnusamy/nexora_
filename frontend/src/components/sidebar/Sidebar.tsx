import { useCallback, useEffect, useRef, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { NAV_ENTRIES } from './navConfig'
import { NavFlyout } from './NavFlyout'
import type { NavLinkItem } from '../../types/navigation'
import { useAccess } from '../../hooks/useAccess'
import { useMediaQuery } from '../../hooks/useMediaQuery'

interface SidebarProps {
  isMobileOpen: boolean
  onNavigate: () => void
}

/** Below this the sidebar is a drawer, and hover doesn't exist. */
const MOBILE_QUERY = '(max-width: 767.98px)'

/** Grace period so the pointer can cross the gap from row to panel. */
const CLOSE_DELAY = 180

interface ResolvedGroup {
  label: string
  icon: string
  children: NavLinkItem[]
}

/** The open group and the row it hangs off. Holding the element here rather
 *  than looking it up from a ref keeps render free of ref reads. */
interface OpenState {
  label: string
  anchor: HTMLButtonElement
  /** Opened by keyboard, so focus should move into the panel. */
  viaKeyboard: boolean
  /** Opened by click, so it stays until dismissed rather than on mouse-out. */
  pinned: boolean
}

export function Sidebar({ isMobileOpen, onNavigate }: SidebarProps) {
  const { can } = useAccess()
  const { pathname } = useLocation()
  const isMobile = useMediaQuery(MOBILE_QUERY)

  const [open, setOpen] = useState<OpenState | null>(null)
  const closeTimer = useRef<number | null>(null)

  const cancelClose = useCallback(() => {
    if (closeTimer.current !== null) {
      window.clearTimeout(closeTimer.current)
      closeTimer.current = null
    }
  }, [])

  const close = useCallback(() => {
    cancelClose()
    setOpen(null)
  }, [cancelClose])

  const scheduleClose = useCallback(() => {
    cancelClose()
    closeTimer.current = window.setTimeout(() => setOpen(null), CLOSE_DELAY)
  }, [cancelClose])

  useEffect(() => cancelClose, [cancelClose])

  // Navigating closes whatever is open. Adjusting during render rather than
  // in an effect avoids a second render pass showing a stale flyout.
  const [lastPath, setLastPath] = useState(pathname)
  if (lastPath !== pathname) {
    setLastPath(pathname)
    if (open) setOpen(null)
  }

  // A pinned flyout is dismissed by clicking anywhere outside it.
  useEffect(() => {
    if (!open?.pinned) return
    const onDown = (event: MouseEvent) => {
      const target = event.target as Element
      if (!target.closest?.('.nav-flyout') && !target.closest?.('.app-nav__row')) close()
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open?.pinned, close])

  // Capability filtering, applied once per render.
  const entries: (ResolvedGroup | ({ kind: 'link' } & NavLinkItem))[] = []
  for (const entry of NAV_ENTRIES) {
    if (entry.kind === 'link') {
      if (!entry.cap || can(entry.cap)) entries.push(entry)
      continue
    }
    const children = entry.children.filter((child) => !child.cap || can(child.cap))
    if (children.length > 0) {
      entries.push({ label: entry.label, icon: entry.icon, children })
    }
  }

  const openGroup = entries.find(
    (entry): entry is ResolvedGroup => !('kind' in entry) && entry.label === open?.label,
  )

  return (
    <aside className={`app-sidebar${isMobileOpen ? ' is-open' : ''}`} aria-label="Main navigation">
      <nav className="app-nav">
        {entries.map((entry) => {
          if ('kind' in entry) {
            return (
              <NavLink
                key={entry.to}
                to={entry.to}
                className={({ isActive }) => `app-nav__row${isActive ? ' is-active' : ''}`}
                onClick={onNavigate}
              >
                <i className={`bi ${entry.icon} app-nav__icon`} aria-hidden="true" />
                <span className="app-nav__label">{entry.label}</span>
              </NavLink>
            )
          }

          const isOpen = open?.label === entry.label
          const containsRoute = entry.children.some(
            (child) => pathname === child.to || pathname.startsWith(`${child.to}/`),
          )

          return (
            <div className="app-nav__item" key={entry.label}>
              <button
                type="button"
                className={`app-nav__row${containsRoute ? ' is-current' : ''}${isOpen ? ' is-open' : ''}`}
                aria-haspopup="menu"
                aria-expanded={isOpen}
                onClick={(event) => {
                  if (isOpen && open?.pinned) {
                    close()
                    return
                  }
                  cancelClose()
                  setOpen({
                    label: entry.label,
                    anchor: event.currentTarget,
                    viaKeyboard: false,
                    pinned: true,
                  })
                }}
                onMouseEnter={(event) => {
                  if (isMobile) return
                  cancelClose()
                  setOpen({
                    label: entry.label,
                    anchor: event.currentTarget,
                    viaKeyboard: false,
                    pinned: false,
                  })
                }}
                onMouseLeave={() => {
                  if (isMobile || open?.pinned) return
                  scheduleClose()
                }}
                onKeyDown={(event) => {
                  if (event.key !== 'ArrowRight' && event.key !== 'ArrowDown') return
                  event.preventDefault()
                  cancelClose()
                  setOpen({
                    label: entry.label,
                    anchor: event.currentTarget,
                    viaKeyboard: true,
                    pinned: true,
                  })
                }}
              >
                <i className={`bi ${entry.icon} app-nav__icon`} aria-hidden="true" />
                <span className="app-nav__label">{entry.label}</span>
                <i className="bi bi-chevron-right app-nav__chevron" aria-hidden="true" />
              </button>

              {/* Mobile has no hover and no room beside the drawer, so children
                  expand inline instead of flying out. */}
              {isMobile && isOpen && (
                <div className="app-nav__sublist">
                  {entry.children.map((child) => (
                    <NavLink
                      key={child.to}
                      to={child.to}
                      className={({ isActive }) => `app-nav__sublink${isActive ? ' is-active' : ''}`}
                      onClick={onNavigate}
                    >
                      <i className={`bi ${child.icon} app-nav__icon`} aria-hidden="true" />
                      <span>{child.label}</span>
                    </NavLink>
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </nav>

      {!isMobile && open && openGroup && (
        <NavFlyout
          label={openGroup.label}
          items={openGroup.children}
          anchor={open.anchor}
          autoFocus={open.viaKeyboard}
          onClose={close}
          onNavigate={onNavigate}
          onPointerEnter={cancelClose}
          onPointerLeave={() => {
            if (!open.pinned) scheduleClose()
          }}
        />
      )}
    </aside>
  )
}
