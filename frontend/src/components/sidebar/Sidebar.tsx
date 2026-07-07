import { useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { NAV_ENTRIES } from './navConfig'
import type { NavLinkItem } from '../../types/navigation'
import { useAccess } from '../../hooks/useAccess'

interface SidebarProps {
  isMobileOpen: boolean
  onNavigate: () => void
}

interface RenderItem {
  kind: 'group' | 'link' | 'divider'
  label: string
  icon: string
  to?: string
  children?: NavLinkItem[]
}

export function Sidebar({ isMobileOpen, onNavigate }: SidebarProps) {
  const { can } = useAccess()
  const location = useLocation()
  
  const [hoveredItem, setHoveredItem] = useState<{ label: string; rect: DOMRect } | null>(null)
  const [activeGroup, setActiveGroup] = useState<{
    label: string
    children: NavLinkItem[]
    rect: DOMRect
  } | null>(null)

  const itemsToRender: RenderItem[] = []

  NAV_ENTRIES.forEach((entry) => {
    let allowedChildren: NavLinkItem[] = []
    if (entry.kind === 'link') {
      if (!entry.cap || can(entry.cap)) {
        allowedChildren = [entry]
      }
    } else {
      allowedChildren = entry.children.filter((child) => !child.cap || can(child.cap))
    }

    if (allowedChildren.length === 0) return

    // Add a divider if we already have items
    if (itemsToRender.length > 0) {
      itemsToRender.push({ kind: 'divider', label: '', icon: '' })
    }

    if (allowedChildren.length === 1) {
      itemsToRender.push({
        kind: 'link',
        label: allowedChildren[0].label,
        icon: allowedChildren[0].icon,
        to: allowedChildren[0].to,
      })
    } else {
      itemsToRender.push({
        kind: 'group',
        label: entry.label,
        icon: entry.icon,
        children: allowedChildren,
      })
    }
  })

  const getPopoverLayout = () => {
    if (!activeGroup) return null

    const headerHeight = 56
    const footerHeight = 0
    const padding = 8
    
    const rect = activeGroup.rect
    const iconCenter = rect.top + rect.height / 2
    
    const childrenCount = activeGroup.children.length
    const estimatedHeight = 44 + childrenCount * 36
    
    let popoverTop = iconCenter - estimatedHeight / 2
    const minTop = headerHeight + padding
    const maxTop = window.innerHeight - footerHeight - padding - estimatedHeight
    
    if (popoverTop < minTop) {
      popoverTop = minTop
    }
    if (popoverTop > maxTop) {
      popoverTop = maxTop
    }
    
    const arrowTop = iconCenter - popoverTop
    
    return {
      top: popoverTop,
      arrowTop,
    }
  }

  return (
    <aside className={`app-sidebar${isMobileOpen ? ' is-open' : ''}`}>
      <nav className="app-sidebar__nav">
        {itemsToRender.map((item, idx) => {
          if (item.kind === 'divider') {
            return <div key={`div-${idx}`} className="app-sidebar__divider" aria-hidden="true" />
          }

          if (item.kind === 'link' && item.to) {
            return (
              <NavLink
                key={item.to}
                to={item.to}
                onClick={onNavigate}
                onMouseEnter={(e) => {
                  const rect = e.currentTarget.getBoundingClientRect()
                  if (!activeGroup) {
                    setHoveredItem({ label: item.label, rect })
                  }
                }}
                onMouseLeave={() => setHoveredItem(null)}
                className={({ isActive }) =>
                  `app-sidebar__link${isActive ? ' active' : ''}`
                }
              >
                <div className="app-sidebar__box">
                  <i className={`bi ${item.icon} app-sidebar__icon`} aria-hidden="true" />
                </div>
              </NavLink>
            )
          }

          if (item.kind === 'group' && item.children) {
            const isGroupActive = item.children.some((child) => location.pathname === child.to)
            const isPopoverOpen = activeGroup?.label === item.label
            
            return (
              <button
                key={item.label}
                type="button"
                onClick={(e) => {
                  if (isPopoverOpen) {
                    setActiveGroup(null)
                  } else {
                    const rect = e.currentTarget.getBoundingClientRect()
                    setActiveGroup({
                      label: item.label,
                      children: item.children || [],
                      rect,
                    })
                    setHoveredItem(null)
                  }
                }}
                onMouseEnter={(e) => {
                  const rect = e.currentTarget.getBoundingClientRect()
                  if (!isPopoverOpen && !activeGroup) {
                    setHoveredItem({ label: item.label, rect })
                  }
                }}
                onMouseLeave={() => setHoveredItem(null)}
                className={`app-sidebar__link${isGroupActive ? ' active' : ''}`}
                aria-expanded={isPopoverOpen}
              >
                <div className="app-sidebar__box">
                  <i className={`bi ${item.icon} app-sidebar__icon`} aria-hidden="true" />
                </div>
              </button>
            )
          }

          return null
        })}
      </nav>

      {hoveredItem && !activeGroup && (
        <div
          className="app-sidebar__floating-tooltip"
          style={{
            top: `${hoveredItem.rect.top + hoveredItem.rect.height / 2}px`,
          }}
        >
          {hoveredItem.label}
        </div>
      )}

      {activeGroup && (() => {
        const layout = getPopoverLayout()
        return (
          <>
            <div className="app-sidebar__popover-backdrop" onClick={() => setActiveGroup(null)} />
            <div
              className="app-sidebar__popover"
              style={{
                top: layout ? `${layout.top}px` : '50%',
                ['--arrow-top' as any]: layout ? `${layout.arrowTop}px` : '50%',
              }}
            >
              <div className="app-sidebar__popover-title">{activeGroup.label}</div>
              <div className="app-sidebar__popover-links">
                {activeGroup.children.map((child) => (
                  <NavLink
                    key={child.to}
                    to={child.to}
                    onClick={() => {
                      setActiveGroup(null)
                      onNavigate()
                    }}
                    className={({ isActive }) =>
                      `app-sidebar__popover-link${isActive ? ' active' : ''}`
                    }
                  >
                    <i className={`bi ${child.icon} app-sidebar__popover-icon`} aria-hidden="true" />
                    <span className="app-sidebar__popover-label">{child.label}</span>
                  </NavLink>
                ))}
              </div>
            </div>
          </>
        )
      })()}
    </aside>
  )
}


