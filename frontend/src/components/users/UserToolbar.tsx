import type { ChangeEvent } from 'react'
import type { StatusFilter } from '../tenants/TenantToolbar'
import type { Tenant } from '../../types/tenant'
import type { Store } from '../../types/store'
import type { Role } from '../../types/role'

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
    <div className="list-toolbar">
      <div className="list-toolbar__search">
        <i className="bi bi-search" aria-hidden="true" />
        <input
          type="search"
          className="form-control"
          placeholder="Search users"
          aria-label="Search users"
          value={search}
          onChange={(event: ChangeEvent<HTMLInputElement>) => onSearchChange(event.target.value)}
        />
      </div>

      <select
        className="form-select list-toolbar__filter"
        aria-label="Filter by tenant"
        value={tenantFilter}
        onChange={(event: ChangeEvent<HTMLSelectElement>) => onTenantFilterChange(event.target.value)}
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
        aria-label="Filter by store"
        value={storeFilter}
        onChange={(event: ChangeEvent<HTMLSelectElement>) => onStoreFilterChange(event.target.value)}
      >
        <option value="all">All stores</option>
        {stores.map((store) => (
          <option key={store.store_id} value={store.store_id}>
            {store.store_name}
          </option>
        ))}
      </select>

      <select
        className="form-select list-toolbar__filter"
        aria-label="Filter by role"
        value={roleFilter}
        onChange={(event: ChangeEvent<HTMLSelectElement>) => onRoleFilterChange(event.target.value)}
      >
        <option value="all">All roles</option>
        {roles.map((role) => (
          <option key={role.role_id} value={role.role_id}>
            {role.role_name}
          </option>
        ))}
      </select>

      <select
        className="form-select list-toolbar__filter"
        aria-label="Filter by status"
        value={status}
        onChange={(event: ChangeEvent<HTMLSelectElement>) => onStatusChange(event.target.value as StatusFilter)}
      >
        <option value="all">All statuses</option>
        <option value="active">Active</option>
        <option value="inactive">Inactive</option>
      </select>

      <button type="button" className="btn btn-primary ms-auto" onClick={onAdd}>
        <i className="bi bi-plus-lg me-1" aria-hidden="true" />
        Add User
      </button>
    </div>
  )
}
