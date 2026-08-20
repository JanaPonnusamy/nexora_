import type { StatusFilter } from '../tenants/TenantToolbar'
import type { Tenant } from '../../types/tenant'
import { FilterToolbar } from '../../design-system/components/FilterToolbar'

interface StoreToolbarProps {
  search: string
  onSearchChange: (value: string) => void
  tenantFilter: string
  onTenantFilterChange: (value: string) => void
  status: StatusFilter
  onStatusChange: (value: StatusFilter) => void
  tenants: Tenant[]
  onAdd: () => void
}

export function StoreToolbar({
  search,
  onSearchChange,
  tenantFilter,
  onTenantFilterChange,
  status,
  onStatusChange,
  tenants,
  onAdd,
}: StoreToolbarProps) {
  return (
    <FilterToolbar
      searchPlaceholder="Search stores"
      searchAriaLabel="Search stores"
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
            ...tenants.map((tenant) => ({
              value: tenant.tenant_id,
              label: tenant.tenant_name,
            })),
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
      actionLabel="Add Store"
      onAction={onAdd}
    />
  )
}
