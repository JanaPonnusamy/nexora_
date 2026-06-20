import { useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { PageHeader } from '../../components/common/PageHeader'
import { EmptyState } from '../../components/common/EmptyState'
import { ErrorState } from '../../components/common/ErrorState'
import { TableSkeleton } from '../../components/common/TableSkeleton'
import { StatusBadge } from '../../components/common/StatusBadge'
import { RoleFormModal } from '../../components/roles/RoleFormModal'
import { useRole } from '../../hooks/useRole'
import { useUsers } from '../../hooks/useUsers'
import { roleService } from '../../services/roleService'
import { formatDateTime } from '../../utils/format'

type WorkspaceTab = 'overview' | 'users'

const TABS: { key: WorkspaceTab; label: string; icon: string }[] = [
  { key: 'overview', label: 'Overview', icon: 'bi-info-circle' },
  { key: 'users', label: 'Users', icon: 'bi-people' },
]

export default function RoleWorkspacePage() {
  const { roleId } = useParams<{ roleId: string }>()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const { role, isLoading, error, reload } = useRole(roleId)
  const {
    users,
    isLoading: usersLoading,
    error: usersError,
    reload: reloadUsers,
  } = useUsers({ roleId })
  const [editing, setEditing] = useState(false)
  const [statusBusy, setStatusBusy] = useState(false)
  const [statusError, setStatusError] = useState<string | null>(null)

  const tabParam = searchParams.get('tab')
  const activeTab: WorkspaceTab = tabParam === 'users' ? 'users' : 'overview'
  const setTab = (tab: WorkspaceTab) =>
    setSearchParams(tab === 'overview' ? {} : { tab }, { replace: true })

  const toggleStatus = async () => {
    if (!role) return
    setStatusBusy(true)
    setStatusError(null)
    try {
      await roleService.setStatus(role.role_id, !role.is_active)
      await reload()
    } catch (err) {
      setStatusError(err instanceof Error ? err.message : 'Failed to update status')
    } finally {
      setStatusBusy(false)
    }
  }

  if (isLoading) {
    return (
      <div className="container-fluid px-0">
        <PageHeader title="Role" breadcrumb={['Platform', 'Roles', '…']} />
        <TableSkeleton rows={4} columns={2} />
      </div>
    )
  }

  if (error || !role) {
    return (
      <div className="container-fluid px-0">
        <PageHeader title="Role" breadcrumb={['Platform', 'Roles', 'Not found']} />
        <ErrorState
          title="Role unavailable"
          description={error ?? 'This role could not be found.'}
          onRetry={reload}
        />
        <div className="text-center mt-3">
          <Link to="/platform/roles" className="btn btn-link">
            Back to Roles
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="container-fluid px-0">
      <div className="workspace-header">
        <div className="workspace-header__info">
          <nav aria-label="breadcrumb">
            <ol className="breadcrumb small mb-2">
              <li className="breadcrumb-item">Platform</li>
              <li className="breadcrumb-item">
                <Link to="/platform/roles">Roles</Link>
              </li>
              <li className="breadcrumb-item active" aria-current="page">
                {role.role_name}
              </li>
            </ol>
          </nav>
          <div className="workspace-header__title">
            <h1 className="h3 mb-0">{role.role_name}</h1>
            <StatusBadge active={role.is_active} />
          </div>
          <div className="workspace-stats">
            <span className="workspace-stat">
              <i className="bi bi-people" aria-hidden="true" />
              <strong className="workspace-stat__value">{role.assigned_users ?? 0}</strong>
              <span>Assigned Users</span>
            </span>
          </div>
        </div>
        <div className="workspace-header__actions">
          <button type="button" className="btn btn-outline-secondary" onClick={() => setEditing(true)}>
            <i className="bi bi-pencil me-1" aria-hidden="true" />
            Edit
          </button>
          <button
            type="button"
            className={`btn ${role.is_active ? 'btn-outline-danger' : 'btn-outline-success'}`}
            onClick={toggleStatus}
            disabled={statusBusy}
          >
            {statusBusy ? (
              <span className="spinner-border spinner-border-sm me-1" aria-hidden="true" />
            ) : (
              <i
                className={`bi ${role.is_active ? 'bi-pause-circle' : 'bi-play-circle'} me-1`}
                aria-hidden="true"
              />
            )}
            {role.is_active ? 'Deactivate' : 'Activate'}
          </button>
        </div>
      </div>

      {statusError && <div className="alert alert-danger py-2">{statusError}</div>}

      <ul className="nav nav-tabs mb-3" role="tablist">
        {TABS.map((tab) => (
          <li className="nav-item" key={tab.key} role="presentation">
            <button
              type="button"
              role="tab"
              id={`tab-${tab.key}`}
              aria-selected={activeTab === tab.key}
              aria-controls={`panel-${tab.key}`}
              className={`nav-link${activeTab === tab.key ? ' active' : ''}`}
              onClick={() => setTab(tab.key)}
            >
              <i className={`bi ${tab.icon} me-1`} aria-hidden="true" />
              {tab.label}
            </button>
          </li>
        ))}
      </ul>

      <div role="tabpanel" id={`panel-${activeTab}`} aria-labelledby={`tab-${activeTab}`}>
        {activeTab === 'overview' && (
          <div className="card">
            <div className="card-body">
              <dl className="row mb-0 workspace-details">
                <dt className="col-sm-3">Role Name</dt>
                <dd className="col-sm-9">{role.role_name}</dd>
                <dt className="col-sm-3">Description</dt>
                <dd className="col-sm-9">{role.description ?? '—'}</dd>
                <dt className="col-sm-3">Status</dt>
                <dd className="col-sm-9">
                  <StatusBadge active={role.is_active} />
                </dd>
                <dt className="col-sm-3">Created Date</dt>
                <dd className="col-sm-9">{formatDateTime(role.created_at)}</dd>
              </dl>
            </div>
          </div>
        )}

        {activeTab === 'users' &&
          (usersLoading ? (
            <TableSkeleton rows={4} columns={3} />
          ) : usersError ? (
            <ErrorState description={usersError} onRetry={reloadUsers} />
          ) : users.length === 0 ? (
            <EmptyState
              icon="bi-people"
              title="No Users Assigned"
              description="Users assigned to this role will appear here."
            />
          ) : (
            <div className="table-responsive">
              <table className="table table-hover align-middle data-table">
                <thead>
                  <tr>
                    <th scope="col">Username</th>
                    <th scope="col">Full Name</th>
                    <th scope="col">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((user) => (
                    <tr
                      key={user.user_id}
                      className="data-row"
                      onClick={() => navigate(`/platform/users/${user.user_id}`)}
                    >
                      <td className="fw-medium">{user.username}</td>
                      <td>{user.full_name}</td>
                      <td>
                        <StatusBadge active={user.is_active} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
      </div>

      {editing && (
        <RoleFormModal
          mode="edit"
          role={role}
          onClose={() => setEditing(false)}
          onSaved={() => {
            setEditing(false)
            void reload()
          }}
        />
      )}
    </div>
  )
}
