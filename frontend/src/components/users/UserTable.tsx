import type { User } from '../../types/user'
import { StatusBadge } from '../common/StatusBadge'
import { UserActions } from './UserActions'
import { formatDateTime } from '../../utils/format'
import { DataTable, type DataTableColumn } from '../common/DataTable'

interface UserTableProps {
  users: User[]
  onView: (user: User) => void
  onEdit: (user: User) => void
  onRoles: (user: User) => void
  onStores: (user: User) => void
}

export function UserTable({ users, onView, onEdit, onRoles, onStores }: UserTableProps) {
  const columns: DataTableColumn<User>[] = [
    {
      key: 'username',
      header: 'Username',
      sortable: true,
      accessor: (user) => <span className="fw-medium">{user.username}</span>,
    },
    {
      key: 'full_name',
      header: 'Full Name',
      sortable: true,
      accessor: (user) => user.full_name,
    },
    {
      key: 'store_count',
      header: 'Stores',
      sortable: true,
      accessor: (user) => user.store_count ?? '—',
    },
    {
      key: 'role_count',
      header: 'Roles',
      sortable: true,
      accessor: (user) => user.role_count ?? '—',
    },
    {
      key: 'last_login',
      header: 'Last Login',
      sortable: true,
      accessor: (user) => formatDateTime(user.last_login),
    },
    {
      key: 'is_active',
      header: 'Status',
      sortable: true,
      accessor: (user) => <StatusBadge active={user.is_active} />,
    },
    {
      key: 'actions',
      header: 'Actions',
      align: 'right',
      accessor: (user) => (
        <UserActions
          userName={user.username}
          onView={() => onView(user)}
          onEdit={() => onEdit(user)}
          onRoles={() => onRoles(user)}
          onStores={() => onStores(user)}
        />
      ),
    },
  ]

  return (
    <div className="d-none d-md-block">
      <DataTable
        columns={columns}
        data={users}
        getRowId={(user) => user.user_id}
        onRowClick={(user) => onView(user)}
        pageSize={10}
        showDensityToggle={true}
      />
    </div>
  )
}
