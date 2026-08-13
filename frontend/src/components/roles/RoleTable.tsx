import type { Role } from '../../types/role'
import { StatusBadge } from '../common/StatusBadge'
import { RoleActions } from './RoleActions'
import { DataTable, type DataTableColumn } from '../common/DataTable'

interface RoleTableProps {
  roles: Role[]
  onView: (role: Role) => void
  onEdit: (role: Role) => void
  onUsers: (role: Role) => void
}

export function RoleTable({ roles, onView, onEdit, onUsers }: RoleTableProps) {
  const columns: DataTableColumn<Role>[] = [
    {
      key: 'role_name',
      header: 'Role Name',
      sortable: true,
      accessor: (role) => <span className="fw-medium">{role.role_name}</span>,
    },
    {
      key: 'description',
      header: 'Description',
      sortable: true,
      accessor: (role) => <span className="text-secondary">{role.description ?? '—'}</span>,
    },
    {
      key: 'assigned_users',
      header: 'Assigned Users',
      sortable: true,
      accessor: (role) => role.assigned_users ?? 0,
    },
    {
      key: 'is_active',
      header: 'Status',
      sortable: true,
      accessor: (role) => <StatusBadge active={role.is_active} />,
    },
    {
      key: 'actions',
      header: 'Actions',
      align: 'right',
      accessor: (role) => (
        <RoleActions
          roleName={role.role_name}
          onView={() => onView(role)}
          onEdit={() => onEdit(role)}
          onUsers={() => onUsers(role)}
        />
      ),
    },
  ]

  return (
    <div className="d-none d-md-block">
      <DataTable
        columns={columns}
        data={roles}
        getRowId={(role) => role.role_id}
        onRowClick={(role) => onView(role)}
        pageSize={10}
        showDensityToggle={true}
      />
    </div>
  )
}
