import type { Tenant } from '../../types/tenant'
import { StatusBadge } from '../common/StatusBadge'
import { TenantActions } from './TenantActions'
import { tenantAccent } from './tenantAccent'

interface TenantTableProps {
  tenants: Tenant[]
  onView: (tenant: Tenant) => void
  onEdit: (tenant: Tenant) => void
  onStores: (tenant: Tenant) => void
  onUsers: (tenant: Tenant) => void
}

export function TenantTable({ tenants, onView, onEdit, onStores, onUsers }: TenantTableProps) {
  return (
    <div className="table-responsive d-none d-md-block">
      <table className="table table-hover align-middle data-table">
        <thead>
          <tr>
            <th scope="col">Tenant Code</th>
            <th scope="col">Abbreviation</th>
            <th scope="col">Tenant Name</th>
            <th scope="col">Database</th>
            <th scope="col">Status</th>
            <th scope="col" className="text-end">Actions</th>
          </tr>
        </thead>
        <tbody>
          {tenants.map((tenant) => (
            <tr
              key={tenant.tenant_id}
              className="data-row"
              onClick={() => onView(tenant)}
            >
              <td>{tenant.tenant_code}</td>
              <td>{tenant.tenant_abbreviation}</td>
              <td className="fw-medium">
                <span className="d-inline-flex align-items-center gap-2">
                  <span className={`tenant-avatar tenant-avatar--${tenantAccent(tenant.tenant_code)}`}>
                    <i className="bi bi-building" aria-hidden="true" />
                  </span>
                  {tenant.tenant_name}
                </span>
              </td>
              <td>
                <code>{tenant.db_name}</code>
              </td>
              <td>
                <StatusBadge active={tenant.is_active} />
              </td>
              <td className="text-end">
                <TenantActions
                  tenantName={tenant.tenant_name}
                  onView={() => onView(tenant)}
                  onEdit={() => onEdit(tenant)}
                  onStores={() => onStores(tenant)}
                  onUsers={() => onUsers(tenant)}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
