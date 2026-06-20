import type { Role } from '../../types/role'
import { StatusBadge } from '../common/StatusBadge'
import { RoleActions } from './RoleActions'

interface RoleTableProps {
  roles: Role[]
  onView: (role: Role) => void
  onEdit: (role: Role) => void
  onUsers: (role: Role) => void
}

export function RoleTable({ roles, onView, onEdit, onUsers }: RoleTableProps) {
  return (
    <div className="table-responsive d-none d-md-block">
      <table className="table table-hover align-middle data-table">
        <thead>
          <tr>
            <th scope="col">Role Name</th>
            <th scope="col">Description</th>
            <th scope="col">Assigned Users</th>
            <th scope="col">Status</th>
            <th scope="col" className="text-end">Actions</th>
          </tr>
        </thead>
        <tbody>
          {roles.map((role) => (
            <tr key={role.role_id} className="data-row" onClick={() => onView(role)}>
              <td className="fw-medium">{role.role_name}</td>
              <td className="text-secondary">{role.description ?? '—'}</td>
              <td>{role.assigned_users ?? 0}</td>
              <td>
                <StatusBadge active={role.is_active} />
              </td>
              <td className="text-end">
                <RoleActions
                  roleName={role.role_name}
                  onView={() => onView(role)}
                  onEdit={() => onEdit(role)}
                  onUsers={() => onUsers(role)}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
