import type { User } from '../../types/user'
import { StatusBadge } from '../common/StatusBadge'
import { UserActions } from './UserActions'
import { formatDateTime } from '../../utils/format'

interface UserTableProps {
  users: User[]
  onView: (user: User) => void
  onEdit: (user: User) => void
  onRoles: (user: User) => void
  onStores: (user: User) => void
}

export function UserTable({ users, onView, onEdit, onRoles, onStores }: UserTableProps) {
  return (
    <div className="table-responsive d-none d-md-block">
      <table className="table table-hover align-middle data-table">
        <thead>
          <tr>
            <th scope="col">Username</th>
            <th scope="col">Full Name</th>
            <th scope="col">Stores</th>
            <th scope="col">Roles</th>
            <th scope="col">Last Login</th>
            <th scope="col">Status</th>
            <th scope="col" className="text-end">Actions</th>
          </tr>
        </thead>
        <tbody>
          {users.map((user) => (
            <tr key={user.user_id} className="data-row" onClick={() => onView(user)}>
              <td className="fw-medium">{user.username}</td>
              <td>{user.full_name}</td>
              <td>{user.store_count ?? '—'}</td>
              <td>{user.role_count ?? '—'}</td>
              <td>{formatDateTime(user.last_login)}</td>
              <td>
                <StatusBadge active={user.is_active} />
              </td>
              <td className="text-end">
                <UserActions
                  userName={user.username}
                  onView={() => onView(user)}
                  onEdit={() => onEdit(user)}
                  onRoles={() => onRoles(user)}
                  onStores={() => onStores(user)}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
