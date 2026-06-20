import type { User } from '../../types/user'
import { StatusBadge } from '../common/StatusBadge'
import { UserActions } from './UserActions'
import { formatDateTime } from '../../utils/format'

interface UserCardListProps {
  users: User[]
  onView: (user: User) => void
  onEdit: (user: User) => void
  onRoles: (user: User) => void
  onStores: (user: User) => void
}

export function UserCardList({ users, onView, onEdit, onRoles, onStores }: UserCardListProps) {
  return (
    <div className="d-md-none vstack gap-2">
      {users.map((user) => (
        <div className="card list-card" key={user.user_id} onClick={() => onView(user)}>
          <div className="card-body">
            <div className="d-flex justify-content-between align-items-start gap-2">
              <div className="min-w-0">
                <div className="fw-semibold text-truncate">{user.full_name}</div>
                <div className="text-secondary small">{user.username}</div>
              </div>
              <StatusBadge active={user.is_active} />
            </div>
            <div className="text-secondary small mt-2 d-flex flex-wrap gap-3">
              <span>
                <i className="bi bi-shop me-1" aria-hidden="true" />
                {user.store_count ?? '—'} stores
              </span>
              <span>
                <i className="bi bi-person-badge me-1" aria-hidden="true" />
                {user.role_count ?? '—'} roles
              </span>
              <span>
                <i className="bi bi-clock-history me-1" aria-hidden="true" />
                {formatDateTime(user.last_login)}
              </span>
            </div>
            <div className="mt-3">
              <UserActions
                userName={user.username}
                onView={() => onView(user)}
                onEdit={() => onEdit(user)}
                onRoles={() => onRoles(user)}
                onStores={() => onStores(user)}
              />
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
