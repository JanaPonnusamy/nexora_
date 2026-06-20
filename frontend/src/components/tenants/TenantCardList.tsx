import type { Tenant } from '../../types/tenant'
import { StatusBadge } from '../common/StatusBadge'
import { TenantActions } from './TenantActions'
import { tenantAccent } from './tenantAccent'

interface TenantCardListProps {
  tenants: Tenant[]
  onView: (tenant: Tenant) => void
  onEdit: (tenant: Tenant) => void
  onStores: (tenant: Tenant) => void
  onUsers: (tenant: Tenant) => void
}

export function TenantCardList({
  tenants,
  onView,
  onEdit,
  onStores,
  onUsers,
}: TenantCardListProps) {
  return (
    <div className="d-md-none vstack gap-2">
      {tenants.map((tenant) => (
        <div className="card list-card" key={tenant.tenant_id} onClick={() => onView(tenant)}>
          <div className="card-body">
            <div className="d-flex justify-content-between align-items-start gap-2">
              <div className="d-flex align-items-center gap-2 min-w-0">
                <span className={`tenant-avatar tenant-avatar--${tenantAccent(tenant.tenant_code)}`}>
                  <i className="bi bi-building" aria-hidden="true" />
                </span>
                <div className="min-w-0">
                  <div className="fw-semibold text-truncate">{tenant.tenant_name}</div>
                  <div className="text-secondary small">
                    {tenant.tenant_code} · {tenant.tenant_abbreviation}
                  </div>
                </div>
              </div>
              <StatusBadge active={tenant.is_active} />
            </div>
            <div className="text-secondary small mt-2">
              <i className="bi bi-database me-1" aria-hidden="true" />
              {tenant.db_name}
            </div>
            <div className="mt-3">
              <TenantActions
                tenantName={tenant.tenant_name}
                onView={() => onView(tenant)}
                onEdit={() => onEdit(tenant)}
                onStores={() => onStores(tenant)}
                onUsers={() => onUsers(tenant)}
              />
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
