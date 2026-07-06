import { NavLink } from 'react-router-dom'
import { NAV_ENTRIES } from './navConfig'
import type { NavLinkItem } from '../../types/navigation'
import { useAccess } from '../../hooks/useAccess'

interface SidebarProps {
  isMobileOpen: boolean
  onNavigate: () => void
}

function SidebarLink({
  item,
  isChild,
  onNavigate,
}: {
  item: NavLinkItem
  isChild?: boolean
  onNavigate: () => void
}) {
  return (
    <NavLink
      to={item.to}
      title={item.label}
      onClick={onNavigate}
      className={({ isActive }) =>
        `app-sidebar__link${isChild ? ' app-sidebar__link--child' : ''}${isActive ? ' active' : ''}`
      }
    >
      <i className={`bi ${item.icon} app-sidebar__icon`} aria-hidden="true" />
      <span className="app-sidebar__label">{item.label}</span>
    </NavLink>
  )
}

export function Sidebar({ isMobileOpen, onNavigate }: SidebarProps) {
  const { can } = useAccess()

  return (
    <aside className={`app-sidebar${isMobileOpen ? ' is-open' : ''}`}>
      <nav className="app-sidebar__nav">
        {NAV_ENTRIES.map((entry) => {
          if (entry.kind === 'link') {
            if (entry.cap && !can(entry.cap)) return null
            return <SidebarLink key={entry.to} item={entry} onNavigate={onNavigate} />
          }
          const children = entry.children.filter((child) => !child.cap || can(child.cap))
          if (children.length === 0) return null
          return (
            <div key={entry.label} className="app-sidebar__group">
              <div className="app-sidebar__group-title" title={entry.label}>
                <i className={`bi ${entry.icon} app-sidebar__icon`} aria-hidden="true" />
                <span className="app-sidebar__label">{entry.label}</span>
              </div>
              {children.map((child) => (
                <SidebarLink key={child.to} item={child} isChild onNavigate={onNavigate} />
              ))}
            </div>
          )
        })}
      </nav>
    </aside>
  )
}
