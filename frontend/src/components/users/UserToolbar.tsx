import type { StatusFilter } from '../tenants/TenantToolbar'
import type { Tenant } from '../../types/tenant'
import type { Store } from '../../types/store'
import type { Role } from '../../types/role'
import { FilterToolbar } from '../../design-system/components/FilterToolbar'

interface UserToolbarProps {
  search: string
  onSearchChange: (value: string) => void
  tenantFilter: string
  onTenantFilterChange: (value: string) => void
  storeFilter: string
  onStoreFilterChange: (value: string) => void
  roleFilter: string
  onRoleFilterChange: (value: string) => void
  status: StatusFilter
  onStatusChange: (value: StatusFilter) => void
  tenants: Tenant[]
  stores: Store[]
  roles: Role[]
  onAdd: () => void
}

export function UserToolbar({
  search,
  onSearchChange,
  tenantFilter,
  onTenantFilterChange,
  storeFilter,
  onStoreFilterChange,
  roleFilter,
  onRoleFilterChange,
  status,
  onStatusChange,
  tenants,
  stores,
  roles,
  onAdd,
}: UserToolbarProps) {
  return (
    <FilterToolbar
      searchPlaceholder="Search users"
      searchAriaLabel="Search users"
      searchValue={search}
      onSearchChange={onSearchChange}
      filters={[
        {
          key: 'tenant',
          ariaLabel: 'Filter by tenant',
          value: tenantFilter,
          onChange: onTenantFilterChange,
          options: [
            { value: 'all', label: 'All tenants' },
            ...tenants.map((tenant) => ({ value: tenant.tenant_id, label: tenant.tenant_name })),
          ],
        },
        {
          key: 'store',
          ariaLabel: 'Filter by store',
          value: storeFilter,
          onChange: onStoreFilterChange,
          options: [
            { value: 'all', label: 'All stores' },
            ...stores.map((store) => ({ value: store.store_id, label: store.store_name })),
          ],
        },
        {
          key: 'role',
          ariaLabel: 'Filter by role',
          value: roleFilter,
          onChange: onRoleFilterChange,
          options: [
            { value: 'all', label: 'All roles' },
            ...roles.map((role) => ({ value: role.role_id, label: role.role_name })),
          ],
        },
        {
          key: 'status',
          ariaLabel: 'Filter by status',
          value: status,
          onChange: (value) => onStatusChange(value as StatusFilter),
          options: [
            { value: 'all', label: 'All statuses' },
            { value: 'active', label: 'Active' },
            { value: 'inactive', label: 'Inactive' },
          ],
        },
      ]}
      actionLabel="Add User"
      onAction={onAdd}
    />
  )
}
