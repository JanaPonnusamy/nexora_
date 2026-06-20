import type { ChangeEvent } from 'react'

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
    <div className="list-toolbar">
      <div className="list-toolbar__search">
        <i className="bi bi-search" aria-hidden="true" />
        <input
          type="search"
          className="form-control"
          placeholder="Search tenants"
          aria-label="Search tenants"
          value={search}
          onChange={(event: ChangeEvent<HTMLInputElement>) => onSearchChange(event.target.value)}
        />
      </div>

      <select
        className="form-select list-toolbar__filter"
        aria-label="Filter by status"
        value={status}
        onChange={(event: ChangeEvent<HTMLSelectElement>) =>
          onStatusChange(event.target.value as StatusFilter)
        }
      >
        <option value="all">All statuses</option>
        <option value="active">Active</option>
        <option value="inactive">Inactive</option>
      </select>

      <button type="button" className="btn btn-primary ms-auto" onClick={onAdd}>
        <i className="bi bi-plus-lg me-1" aria-hidden="true" />
        Add Tenant
      </button>
    </div>
  )
}
