import { useMemo, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { PageHeader } from '../../components/common/PageHeader'
import { EmptyState } from '../../components/common/EmptyState'
import { ErrorState } from '../../components/common/ErrorState'
import { TableSkeleton } from '../../components/common/TableSkeleton'
import { StatusBadge } from '../../components/common/StatusBadge'
import { Skeleton } from '../../components/common/Skeleton'
import { UserFormModal } from '../../components/users/UserFormModal'
import { useUser } from '../../hooks/useUser'
import { useUserRoles } from '../../hooks/useUserRoles'
import { userService } from '../../services/userService'
import { formatDateTime } from '../../utils/format'

type WorkspaceTab = 'overview' | 'roles' | 'stores'

const TABS: { key: WorkspaceTab; label: string; icon: string }[] = [
  { key: 'overview', label: 'Overview', icon: 'bi-info-circle' },
  { key: 'roles', label: 'Roles', icon: 'bi-person-badge' },
  { key: 'stores', label: 'Store Access', icon: 'bi-shop' },
]

export default function UserWorkspacePage() {
  const { userId } = useParams<{ userId: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  const { user, isLoading, error, reload } = useUser(userId)
  const {
    assignments,
    isLoading: assignmentsLoading,
    error: assignmentsError,
    reload: reloadAssignments,
  } = useUserRoles(userId)
  const [editing, setEditing] = useState(false)
  const [statusBusy, setStatusBusy] = useState(false)
  const [statusError, setStatusError] = useState<string | null>(null)

  const tabParam = searchParams.get('tab')
  const activeTab: WorkspaceTab =
    tabParam === 'roles' || tabParam === 'stores' ? tabParam : 'overview'
  const setTab = (tab: WorkspaceTab) =>
    setSearchParams(tab === 'overview' ? {} : { tab }, { replace: true })

  const uniqueStores = useMemo(() => {
    const map = new Map<string, { store_id: string; store_code: string; store_name: string }>()
    assignments.forEach((assignment) => {
      if (!map.has(assignment.store_id)) {
        map.set(assignment.store_id, {
          store_id: assignment.store_id,
          store_code: assignment.store_code,
          store_name: assignment.store_name,
        })
      }
    })
    return [...map.values()]
  }, [assignments])

  const uniqueRoleCount = useMemo(
    () => new Set(assignments.map((assignment) => assignment.role_id)).size,
    [assignments],
  )

  const toggleStatus = async () => {
    if (!user) return
    setStatusBusy(true)
    setStatusError(null)
    try {
      await userService.setStatus(user.user_id, !user.is_active)
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
        <PageHeader title="User" breadcrumb={['Platform', 'Users', '…']} />
        <TableSkeleton rows={4} columns={2} />
      </div>
    )
  }

  if (error || !user) {
    return (
      <div className="container-fluid px-0">
        <PageHeader title="User" breadcrumb={['Platform', 'Users', 'Not found']} />
        <ErrorState
          title="User unavailable"
          description={error ?? 'This user could not be found.'}
          onRetry={reload}
        />
        <div className="text-center mt-3">
          <Link to="/platform/users" className="btn btn-link">
            Back to Users
          </Link>
        </div>
      </div>
    )
  }

  const renderStat = (
    icon: string,
    label: string,
    value: number,
    title: string,
  ) => (
    <span className="workspace-stat" title={title}>
      <i className={`bi ${icon}`} aria-hidden="true" />
      {assignmentsLoading ? (
        <Skeleton width="1.5rem" height="0.9rem" />
      ) : (
        <strong className="workspace-stat__value">{assignmentsError ? '—' : value}</strong>
      )}
      <span>{label}</span>
    </span>
  )

  return (
    <div className="container-fluid px-0">
      <div className="workspace-header">
        <div className="workspace-header__info">
          <nav aria-label="breadcrumb">
            <ol className="breadcrumb small mb-2">
              <li className="breadcrumb-item">Platform</li>
              <li className="breadcrumb-item">
                <Link to="/platform/users">Users</Link>
              </li>
              <li className="breadcrumb-item active" aria-current="page">
                {user.full_name}
              </li>
            </ol>
          </nav>
          <div className="workspace-header__title">
            <h1 className="h3 mb-0">{user.full_name}</h1>
            <StatusBadge active={user.is_active} />
          </div>
          <div className="workspace-stats">
            <span className="workspace-stat">
              <i className="bi bi-person" aria-hidden="true" />
              <span className="workspace-stat__value">{user.username}</span>
              <span>Username</span>
            </span>
            {renderStat('bi-shop', 'Stores', uniqueStores.length, 'Stores this user can access')}
            {renderStat('bi-person-badge', 'Roles', uniqueRoleCount, 'Roles assigned to this user')}
          </div>
        </div>
        <div className="workspace-header__actions">
          <button type="button" className="btn btn-outline-secondary" onClick={() => setEditing(true)}>
            <i className="bi bi-pencil me-1" aria-hidden="true" />
            Edit
          </button>
          <button
            type="button"
            className={`btn ${user.is_active ? 'btn-outline-danger' : 'btn-outline-success'}`}
            onClick={toggleStatus}
            disabled={statusBusy}
          >
            {statusBusy ? (
              <span className="spinner-border spinner-border-sm me-1" aria-hidden="true" />
            ) : (
              <i
                className={`bi ${user.is_active ? 'bi-pause-circle' : 'bi-play-circle'} me-1`}
                aria-hidden="true"
              />
            )}
            {user.is_active ? 'Deactivate' : 'Activate'}
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
                <dt className="col-sm-3">Username</dt>
                <dd className="col-sm-9">{user.username}</dd>
                <dt className="col-sm-3">Full Name</dt>
                <dd className="col-sm-9">{user.full_name}</dd>
                <dt className="col-sm-3">Last Login</dt>
                <dd className="col-sm-9">{formatDateTime(user.last_login)}</dd>
                <dt className="col-sm-3">Status</dt>
                <dd className="col-sm-9">
                  <StatusBadge active={user.is_active} />
                </dd>
              </dl>
            </div>
          </div>
        )}

        {activeTab === 'roles' &&
          (assignmentsLoading ? (
            <TableSkeleton rows={4} columns={2} />
          ) : assignmentsError ? (
            <ErrorState description={assignmentsError} onRetry={reloadAssignments} />
          ) : assignments.length === 0 ? (
            <EmptyState
              icon="bi-person-badge"
              title="No Roles Found"
              description="Roles assigned to this user will appear here."
            />
          ) : (
            <div className="table-responsive">
              <table className="table table-hover align-middle data-table">
                <thead>
                  <tr>
                    <th scope="col">Role</th>
                    <th scope="col">Store</th>
                  </tr>
                </thead>
                <tbody>
                  {assignments.map((assignment) => (
                    <tr key={`${assignment.role_id}-${assignment.store_id}`}>
                      <td className="fw-medium">{assignment.role_name}</td>
                      <td>{assignment.store_name}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}

        {activeTab === 'stores' &&
          (assignmentsLoading ? (
            <TableSkeleton rows={4} columns={2} />
          ) : assignmentsError ? (
            <ErrorState description={assignmentsError} onRetry={reloadAssignments} />
          ) : uniqueStores.length === 0 ? (
            <EmptyState
              icon="bi-shop"
              title="No Store Access Found"
              description="Stores this user can access will appear here."
            />
          ) : (
            <div className="table-responsive">
              <table className="table table-hover align-middle data-table">
                <thead>
                  <tr>
                    <th scope="col">Store Code</th>
                    <th scope="col">Store Name</th>
                  </tr>
                </thead>
                <tbody>
                  {uniqueStores.map((store) => (
                    <tr key={store.store_id}>
                      <td>{store.store_code}</td>
                      <td className="fw-medium">{store.store_name}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
      </div>

      {editing && (
        <UserFormModal
          mode="edit"
          user={user}
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
