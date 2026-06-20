import type { ChangeEvent } from 'react'
import type { StatusFilter } from '../tenants/TenantToolbar'
import type { Tenant } from '../../types/tenant'

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
    <div className="list-toolbar">
      <div className="list-toolbar__search">
        <i className="bi bi-search" aria-hidden="true" />
        <input
          type="search"
          className="form-control"
          placeholder="Search stores"
          aria-label="Search stores"
          value={search}
          onChange={(event: ChangeEvent<HTMLInputElement>) => onSearchChange(event.target.value)}
        />
      </div>

      <select
        className="form-select list-toolbar__filter"
        aria-label="Filter by tenant"
        value={tenantFilter}
        onChange={(event: ChangeEvent<HTMLSelectElement>) =>
          onTenantFilterChange(event.target.value)
        }
      >
        <option value="all">All tenants</option>
        {tenants.map((tenant) => (
          <option key={tenant.tenant_id} value={tenant.tenant_id}>
            {tenant.tenant_name}
          </option>
        ))}
      </select>

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
        Add Store
      </button>
    </div>
  )
}
