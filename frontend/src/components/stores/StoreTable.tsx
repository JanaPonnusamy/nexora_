import type { Store } from '../../types/store'
import { StatusBadge } from '../common/StatusBadge'
import { StoreActions } from './StoreActions'
import { DataTable, type DataTableColumn } from '../common/DataTable'

interface StoreTableProps {
  stores: Store[]
  getTenantName: (tenantId: string) => string
  onView: (store: Store) => void
  onEdit: (store: Store) => void
  onUsers: (store: Store) => void
  onRoles: (store: Store) => void
}

export function StoreTable({
  stores,
  getTenantName,
  onView,
  onEdit,
  onUsers,
  onRoles,
}: StoreTableProps) {
  const columns: DataTableColumn<Store>[] = [
    {
      key: 'store_code',
      header: 'Store Code',
      sortable: true,
      accessor: (store) => store.store_code,
    },
    {
      key: 'store_name',
      header: 'Store Name',
      sortable: true,
      accessor: (store) => <span className="fw-medium">{store.store_name}</span>,
    },
    {
      key: 'tenant_id',
      header: 'Tenant',
      sortable: true,
      sortValue: (store) => getTenantName(store.tenant_id),
      accessor: (store) => getTenantName(store.tenant_id),
    },
    {
      key: 'server_name',
      header: 'Server',
      sortable: true,
      accessor: (store) => store.server_name,
    },
    {
      key: 'database_name',
      header: 'Database',
      sortable: true,
      accessor: (store) => <code>{store.database_name}</code>,
    },
    {
      key: 'is_active',
      header: 'Status',
      sortable: true,
      accessor: (store) => <StatusBadge active={store.is_active} />,
    },
    {
      key: 'actions',
      header: 'Actions',
      align: 'right',
      accessor: (store) => (
        <StoreActions
          storeName={store.store_name}
          onView={() => onView(store)}
          onEdit={() => onEdit(store)}
          onUsers={() => onUsers(store)}
          onRoles={() => onRoles(store)}
        />
      ),
    },
  ]

  return (
    <div className="d-none d-md-block">
      <DataTable
        columns={columns}
        data={stores}
        getRowId={(store) => store.store_id}
        onRowClick={(store) => onView(store)}
        pageSize={10}
        showDensityToggle={true}
      />
    </div>
  )
}
