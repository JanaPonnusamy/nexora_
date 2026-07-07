import type { NavEntry } from '../../types/navigation'

/** Grouped navigation sections (UI-02 — stronger operational hierarchy). */
export const NAV_ENTRIES: NavEntry[] = [
  {
    kind: 'group',
    label: 'Platform',
    icon: 'bi-grid-1x2',
    cap: 'PLATFORM',
    children: [
      { label: 'Overview', to: '/overview', icon: 'bi-speedometer2', cap: 'PLATFORM' },
      { label: 'Tenants', to: '/platform/tenants', icon: 'bi-building', cap: 'PLATFORM' },
      { label: 'Stores', to: '/platform/stores', icon: 'bi-shop', cap: 'PLATFORM' },
      { label: 'Users', to: '/platform/users', icon: 'bi-people', cap: 'PLATFORM' },
      { label: 'Roles', to: '/platform/roles', icon: 'bi-person-badge', cap: 'PLATFORM' },
    ],
  },
  {
    kind: 'group',
    label: 'Inventory',
    icon: 'bi-box-seam',
    cap: 'INVENTORY',
    children: [
      { label: 'Stock Availability', to: '/stock-availability', icon: 'bi-box-seam', cap: 'INVENTORY' },
    ],
  },
  {
    kind: 'group',
    label: 'Procurement',
    icon: 'bi-cart-check',
    cap: 'PROCUREMENT_WORKSPACE',
    children: [
      { label: 'Cycle Management', to: '/procurement/cycles', icon: 'bi-diagram-3', cap: 'PROCUREMENT_ADMIN' },
      { label: 'Refresh Management', to: '/procurement/refreshes', icon: 'bi-arrow-repeat', cap: 'PROCUREMENT_ADMIN' },
      { label: 'Purchase Manager', to: '/procurement/workspace', icon: 'bi-cart-check', cap: 'PROCUREMENT_WORKSPACE' },
      { label: 'Product Intelligence', to: '/procurement/intelligence', icon: 'bi-cpu', cap: 'PROCUREMENT_WORKSPACE' },
    ],
  },
  {
    kind: 'group',
    label: 'Master Data',
    icon: 'bi-diagram-3',
    cap: 'PRODUCT_MAPPING',
    children: [
      { label: 'Product Mapping', to: '/product-mapping', icon: 'bi-diagram-3', cap: 'PRODUCT_MAPPING' },
    ],
  },
  {
    kind: 'group',
    label: 'Sync',
    icon: 'bi-arrow-repeat',
    cap: 'SYNC',
    children: [
      { label: 'Sync Administration', to: '/sync-administration', icon: 'bi-arrow-repeat', cap: 'SYNC' },
    ],
  },
  {
    kind: 'group',
    label: 'Administration',
    icon: 'bi-sliders',
    cap: 'ADMINISTRATION',
    children: [
      { label: 'Modules', to: '/administration/modules', icon: 'bi-boxes', cap: 'ADMINISTRATION' },
      { label: 'Permissions', to: '/administration/permissions', icon: 'bi-shield-lock', cap: 'ADMINISTRATION' },
    ],
  },
  {
    kind: 'group',
    label: 'System',
    icon: 'bi-gear',
    children: [
      { label: 'Reports', to: '/reports', icon: 'bi-bar-chart', cap: 'REPORTS' },
      { label: 'Settings', to: '/settings', icon: 'bi-gear', cap: 'SETTINGS' },
    ],
  },
]
