import type { StatusFilter } from '../tenants/TenantToolbar'
import { FilterToolbar } from '../../design-system/components/FilterToolbar'

interface ModuleToolbarProps {
  search: string
  onSearchChange: (value: string) => void
  status: StatusFilter
  onStatusChange: (value: StatusFilter) => void
  onAdd: () => void
}

export function ModuleToolbar({ search, onSearchChange, status, onStatusChange, onAdd }: ModuleToolbarProps) {
  return (
    <FilterToolbar
      searchPlaceholder="Search modules"
      searchAriaLabel="Search modules"
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
      actionLabel="Add Module"
      onAction={onAdd}
    />
  )
}
