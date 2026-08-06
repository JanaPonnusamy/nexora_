import { FilterToolbar } from '../../design-system/components/FilterToolbar'

export type StatusFilter = 'all' | 'active' | 'inactive'

interface TenantToolbarProps {
  search: string
  onSearchChange: (value: string) => void
  status: StatusFilter
  onStatusChange: (value: StatusFilter) => void
  onAdd: () => void
}

export function TenantToolbar({
  search,
  onSearchChange,
  status,
  onStatusChange,
  onAdd,
}: TenantToolbarProps) {
  return (
    <FilterToolbar
      searchPlaceholder="Search tenants"
      searchAriaLabel="Search tenants"
      searchValue={search}
      onSearchChange={onSearchChange}
      filters={[
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
      actionLabel="Add Tenant"
      onAction={onAdd}
    />
  )
}
