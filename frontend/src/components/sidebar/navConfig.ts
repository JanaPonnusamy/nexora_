import type { NavEntry } from '../../types/navigation'

/** Navigation structure per design1.md (single source of truth). */
export const NAV_ENTRIES: NavEntry[] = [
  { kind: 'link', label: 'Platform Overview', to: '/overview', icon: 'bi-grid-1x2' },
  {
    kind: 'group',
    label: 'Platform',
    icon: 'bi-buildings',
    children: [
      { label: 'Tenants', to: '/platform/tenants', icon: 'bi-building' },
      { label: 'Stores', to: '/platform/stores', icon: 'bi-shop' },
      { label: 'Users', to: '/platform/users', icon: 'bi-people' },
      { label: 'Roles', to: '/platform/roles', icon: 'bi-person-badge' },
    ],
  },
  {
    kind: 'group',
    label: 'Administration',
    icon: 'bi-sliders',
    children: [
      { label: 'Modules', to: '/administration/modules', icon: 'bi-boxes' },
      { label: 'Permissions', to: '/administration/permissions', icon: 'bi-shield-lock' },
    ],
  },
  { kind: 'link', label: 'Sync Administration', to: '/sync-administration', icon: 'bi-arrow-repeat' },
  { kind: 'link', label: 'Reports', to: '/reports', icon: 'bi-bar-chart' },
  { kind: 'link', label: 'Settings', to: '/settings', icon: 'bi-gear' },
]
