import type { Store } from '../../types/store'
import { StatusBadge } from '../common/StatusBadge'
import { StoreActions } from './StoreActions'

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
  return (
    <div className="table-responsive d-none d-md-block">
      <table className="table table-hover align-middle data-table">
        <thead>
          <tr>
            <th scope="col">Store Code</th>
            <th scope="col">Store Name</th>
            <th scope="col">Tenant</th>
            <th scope="col">Server</th>
            <th scope="col">Database</th>
            <th scope="col">Status</th>
            <th scope="col" className="text-end">Actions</th>
          </tr>
        </thead>
        <tbody>
          {stores.map((store) => (
            <tr key={store.store_id} className="data-row" onClick={() => onView(store)}>
              <td>{store.store_code}</td>
              <td className="fw-medium">{store.store_name}</td>
              <td>{getTenantName(store.tenant_id)}</td>
              <td>{store.server_name}</td>
              <td>
                <code>{store.database_name}</code>
              </td>
              <td>
                <StatusBadge active={store.is_active} />
              </td>
              <td className="text-end">
                <StoreActions
                  storeName={store.store_name}
                  onView={() => onView(store)}
                  onEdit={() => onEdit(store)}
                  onUsers={() => onUsers(store)}
                  onRoles={() => onRoles(store)}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
