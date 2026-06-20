import type { Store } from '../../types/store'
import { StatusBadge } from '../common/StatusBadge'
import { StoreActions } from './StoreActions'

interface StoreCardListProps {
  stores: Store[]
  getTenantName: (tenantId: string) => string
  onView: (store: Store) => void
  onEdit: (store: Store) => void
  onUsers: (store: Store) => void
  onRoles: (store: Store) => void
}

export function StoreCardList({
  stores,
  getTenantName,
  onView,
  onEdit,
  onUsers,
  onRoles,
}: StoreCardListProps) {
  return (
    <div className="d-md-none vstack gap-2">
      {stores.map((store) => (
        <div className="card list-card" key={store.store_id} onClick={() => onView(store)}>
          <div className="card-body">
            <div className="d-flex justify-content-between align-items-start gap-2">
              <div className="min-w-0">
                <div className="fw-semibold text-truncate">{store.store_name}</div>
                <div className="text-secondary small">
                  {store.store_code} · {getTenantName(store.tenant_id)}
                </div>
              </div>
              <StatusBadge active={store.is_active} />
            </div>
            <div className="text-secondary small mt-2">
              <i className="bi bi-hdd-network me-1" aria-hidden="true" />
              {store.server_name} · {store.database_name}
            </div>
            <div className="mt-3">
              <StoreActions
                storeName={store.store_name}
                onView={() => onView(store)}
                onEdit={() => onEdit(store)}
                onUsers={() => onUsers(store)}
                onRoles={() => onRoles(store)}
              />
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
