import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { NavLink } from 'react-router-dom'
import type { NavLinkItem } from '../../types/navigation'

interface NavFlyoutProps {
  /** Group title shown as the flyout's own heading. */
  label: string
  items: NavLinkItem[]
  /** The sidebar row this flyout belongs to — used as the anchor. */
  anchor: HTMLElement
  onClose: () => void
  onNavigate: () => void
  /** Move focus into the list on open (keyboard entry, not hover). */
  autoFocus: boolean
  onPointerEnter: () => void
  onPointerLeave: () => void
}

const VIEWPORT_MARGIN = 8

/**
 * Submenu panel for one sidebar group.
 *
 * Rendered through a portal rather than inside the sidebar: `.app-sidebar`
 * scrolls, and any absolutely-positioned child would be clipped by its
 * overflow. Portalling also keeps it above the header without a z-index war.
 */
export function NavFlyout({
  label,
  items,
  anchor,
  onClose,
  onNavigate,
  autoFocus,
  onPointerEnter,
  onPointerLeave,
}: NavFlyoutProps) {
  const panelRef = useRef<HTMLDivElement>(null)
  const [position, setPosition] = useState<{ top: number; left: number } | null>(null)

  // Position against the anchor, flipping up when the panel would run past
  // the viewport floor. Procurement carries eight children, so this matters.
  useLayoutEffect(() => {
    const panel = panelRef.current
    if (!panel) return

    const place = () => {
      const rect = anchor.getBoundingClientRect()
      const height = panel.offsetHeight
      const maxTop = window.innerHeight - height - VIEWPORT_MARGIN
      setPosition({
        top: Math.max(VIEWPORT_MARGIN, Math.min(rect.top, maxTop)),
        left: rect.right,
      })
    }

    place()
    window.addEventListener('resize', place)
    window.addEventListener('scroll', place, true)
    return () => {
      window.removeEventListener('resize', place)
      window.removeEventListener('scroll', place, true)
    }
  }, [anchor, items.length])

  useEffect(() => {
    if (!autoFocus) return
    panelRef.current?.querySelector<HTMLAnchorElement>('a')?.focus()
  }, [autoFocus])

  // Roving focus within the panel; Escape hands focus back to the row.
  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault()
      onClose()
      anchor.focus()
      return
    }
    if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return

    event.preventDefault()
    const links = Array.from(panelRef.current?.querySelectorAll<HTMLAnchorElement>('a') ?? [])
    if (links.length === 0) return
    const index = links.indexOf(document.activeElement as HTMLAnchorElement)
    const step = event.key === 'ArrowDown' ? 1 : -1
    const next = (index + step + links.length) % links.length
    links[next].focus()
  }

  return createPortal(
    <div
      ref={panelRef}
      className="nav-flyout"
      role="menu"
      aria-label={label}
      onKeyDown={onKeyDown}
      onMouseEnter={onPointerEnter}
      onMouseLeave={onPointerLeave}
      style={{
        top: position?.top ?? 0,
        left: position?.left ?? 0,
        visibility: position ? 'visible' : 'hidden',
      }}
    >
      <p className="nav-flyout__title">{label}</p>
      <div className="nav-flyout__list">
        {items.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            role="menuitem"
            className={({ isActive }) => `nav-flyout__link${isActive ? ' is-active' : ''}`}
            onClick={() => {
              onNavigate()
              onClose()
            }}
          >
            <i className={`bi ${item.icon} nav-flyout__icon`} aria-hidden="true" />
            <span>{item.label}</span>
          </NavLink>
        ))}
      </div>
    </div>,
    document.body,
  )
}
