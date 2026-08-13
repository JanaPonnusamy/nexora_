import { NAV_ENTRIES } from './navConfig'
import type { NavLinkItem } from '../../types/navigation'

export interface NavDestination extends NavLinkItem {
  /** Parent group label, absent for top-level links. */
  group?: string
}

/** Every reachable destination, flattened. Derived from NAV_ENTRIES so the
 *  header context and the command palette can never drift from the sidebar. */
export const NAV_DESTINATIONS: NavDestination[] = NAV_ENTRIES.flatMap((entry): NavDestination[] =>
  entry.kind === 'link'
    ? [{ label: entry.label, to: entry.to, icon: entry.icon, cap: entry.cap }]
    : entry.children.map((child) => ({ ...child, group: entry.label })),
)

/**
 * The destination a pathname belongs to. Prefers the longest matching `to`,
 * so `/procurement/workspace` doesn't resolve to a shorter `/procurement`.
 */
export function findDestination(pathname: string): NavDestination | null {
  let best: NavDestination | null = null
  for (const destination of NAV_DESTINATIONS) {
    const isMatch = pathname === destination.to || pathname.startsWith(`${destination.to}/`)
    if (isMatch && (!best || destination.to.length > best.to.length)) {
      best = destination
    }
  }
  return best
}
