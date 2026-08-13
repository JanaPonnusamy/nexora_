import type { Tenant } from '../../types/tenant'
import { StatusBadge } from '../common/StatusBadge'
import { TenantActions } from './TenantActions'
import { tenantAccent } from './tenantAccent'
import { DataTable, type DataTableColumn } from '../common/DataTable'

interface TenantTableProps {
  tenants: Tenant[]
  onView: (tenant: Tenant) => void
  onEdit: (tenant: Tenant) => void
  onStores: (tenant: Tenant) => void
  onUsers: (tenant: Tenant) => void
}

export function TenantTable({ tenants, onView, onEdit, onStores, onUsers }: TenantTableProps) {
  const columns: DataTableColumn<Tenant>[] = [
    {
      key: 'tenant_code',
      header: 'Tenant Code',
      sortable: true,
      accessor: (tenant) => tenant.tenant_code,
    },
    {
      key: 'tenant_abbreviation',
      header: 'Abbreviation',
      sortable: true,
      accessor: (tenant) => tenant.tenant_abbreviation,
    },
    {
      key: 'tenant_name',
      header: 'Tenant Name',
      sortable: true,
      accessor: (tenant) => (
        <span className="d-inline-flex align-items-center gap-2 fw-medium">
          <span className={`tenant-avatar tenant-avatar--${tenantAccent(tenant.tenant_code)}`}>
            <i className="bi bi-building" aria-hidden="true" />
          </span>
          {tenant.tenant_name}
        </span>
      ),
    },
    {
      key: 'db_name',
      header: 'Database',
      sortable: true,
      accessor: (tenant) => <code>{tenant.db_name}</code>,
    },
    {
      key: 'is_active',
      header: 'Status',
      sortable: true,
      accessor: (tenant) => <StatusBadge active={tenant.is_active} />,
    },
    {
      key: 'actions',
      header: 'Actions',
      align: 'right',
      accessor: (tenant) => (
        <TenantActions
          tenantName={tenant.tenant_name}
          onView={() => onView(tenant)}
          onEdit={() => onEdit(tenant)}
          onStores={() => onStores(tenant)}
          onUsers={() => onUsers(tenant)}
        />
      ),
    },
  ]

  return (
    <div className="d-none d-md-block">
      <DataTable
        columns={columns}
        data={tenants}
        getRowId={(tenant) => tenant.tenant_id}
        onRowClick={(tenant) => onView(tenant)}
        pageSize={10}
        showDensityToggle={true}
      />
    </div>
  )
}
