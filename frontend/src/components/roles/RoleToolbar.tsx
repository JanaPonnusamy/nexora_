import type { StatusFilter } from '../tenants/TenantToolbar'
import { FilterToolbar } from '../../design-system/components/FilterToolbar'

interface RoleToolbarProps {
  search: string
  onSearchChange: (value: string) => void
  status: StatusFilter
  onStatusChange: (value: StatusFilter) => void
  onAdd: () => void
}

export function RoleToolbar({ search, onSearchChange, status, onStatusChange, onAdd }: RoleToolbarProps) {
  return (
    <FilterToolbar
      searchPlaceholder="Search roles"
      searchAriaLabel="Search roles"
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
      actionLabel="Add Role"
      onAction={onAdd}
    />
  )
}
