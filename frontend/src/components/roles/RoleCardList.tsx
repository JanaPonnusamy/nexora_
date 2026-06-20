import type { Role } from '../../types/role'
import { StatusBadge } from '../common/StatusBadge'
import { RoleActions } from './RoleActions'

interface RoleCardListProps {
  roles: Role[]
  onView: (role: Role) => void
  onEdit: (role: Role) => void
  onUsers: (role: Role) => void
}

export function RoleCardList({ roles, onView, onEdit, onUsers }: RoleCardListProps) {
  return (
    <div className="d-md-none vstack gap-2">
      {roles.map((role) => (
        <div className="card list-card" key={role.role_id} onClick={() => onView(role)}>
          <div className="card-body">
            <div className="d-flex justify-content-between align-items-start gap-2">
              <div className="min-w-0">
                <div className="fw-semibold text-truncate">{role.role_name}</div>
                <div className="text-secondary small text-truncate">{role.description ?? '—'}</div>
              </div>
              <StatusBadge active={role.is_active} />
            </div>
            <div className="text-secondary small mt-2">
              <i className="bi bi-people me-1" aria-hidden="true" />
              {role.assigned_users ?? 0} assigned users
            </div>
            <div className="mt-3">
              <RoleActions
                roleName={role.role_name}
                onView={() => onView(role)}
                onEdit={() => onEdit(role)}
                onUsers={() => onUsers(role)}
              />
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
