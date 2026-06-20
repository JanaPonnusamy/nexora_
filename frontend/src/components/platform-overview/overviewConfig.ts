import type { NavigationCardItem, QuickAction } from '../../types/platform'

export interface KpiDefinition {
  key: string
  label: string
  icon: string
}

/** KPI cards shown on the Platform Overview (design Screen 01). */
export const KPI_DEFINITIONS: KpiDefinition[] = [
  { key: 'tenants', label: 'Tenants', icon: 'bi-building' },
  { key: 'stores', label: 'Stores', icon: 'bi-shop' },
  { key: 'users', label: 'Users', icon: 'bi-people' },
  { key: 'roles', label: 'Roles', icon: 'bi-person-badge' },
  { key: 'modules', label: 'Modules', icon: 'bi-boxes' },
]

export const QUICK_ACTIONS: QuickAction[] = [
  { label: 'Create Tenant', description: 'Add a new organization', icon: 'bi-building-add', to: '/platform/tenants' },
  { label: 'Create Store', description: 'Register a new store', icon: 'bi-shop-window', to: '/platform/stores' },
  { label: 'Create User', description: 'Invite a team member', icon: 'bi-person-plus', to: '/platform/users' },
  { label: 'Create Role', description: 'Define a platform role', icon: 'bi-person-badge', to: '/platform/roles' },
  { label: 'Manage Permissions', description: 'Configure access control', icon: 'bi-shield-lock', to: '/administration/permissions' },
]

export const NAVIGATION_CARDS: NavigationCardItem[] = [
  { label: 'Tenants', description: 'Manage organizations', icon: 'bi-building', to: '/platform/tenants' },
  { label: 'Stores', description: 'Manage stores under tenants', icon: 'bi-shop', to: '/platform/stores' },
  { label: 'Users', description: 'Manage users and assignments', icon: 'bi-people', to: '/platform/users' },
  { label: 'Roles', description: 'Manage platform roles', icon: 'bi-person-badge', to: '/platform/roles' },
  { label: 'Modules', description: 'Manage the module registry', icon: 'bi-boxes', to: '/administration/modules' },
  { label: 'Permissions', description: 'Security administration', icon: 'bi-shield-lock', to: '/administration/permissions' },
  { label: 'Reports', description: 'Platform reports', icon: 'bi-bar-chart', to: '/reports' },
  { label: 'Settings', description: 'Platform configuration', icon: 'bi-gear', to: '/settings' },
]
