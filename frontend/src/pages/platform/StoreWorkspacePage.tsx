import { useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { PageHeader } from '../../components/common/PageHeader'
import { EmptyState } from '../../components/common/EmptyState'
import { ErrorState } from '../../components/common/ErrorState'
import { TableSkeleton } from '../../components/common/TableSkeleton'
import { StatusBadge } from '../../components/common/StatusBadge'
import { StoreFormModal } from '../../components/stores/StoreFormModal'
import { useStore } from '../../hooks/useStore'
import { useTenant } from '../../hooks/useTenant'
import { useTenants } from '../../hooks/useTenants'
import { storeService } from '../../services/storeService'

type WorkspaceTab = 'overview' | 'users' | 'roles'

const TABS: { key: WorkspaceTab; label: string; icon: string }[] = [
  { key: 'overview', label: 'Overview', icon: 'bi-info-circle' },
  { key: 'users', label: 'Users', icon: 'bi-people' },
  { key: 'roles', label: 'Roles', icon: 'bi-person-badge' },
]

export default function StoreWorkspacePage() {
  const { storeId } = useParams<{ storeId: string }>()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const { store, isLoading, error, reload } = useStore(storeId)
  const { tenant } = useTenant(store?.tenant_id)
  const { tenants } = useTenants()
  const [editing, setEditing] = useState(false)
  const [statusBusy, setStatusBusy] = useState(false)
  const [statusError, setStatusError] = useState<string | null>(null)

  const tabParam = searchParams.get('tab')
  const activeTab: WorkspaceTab =
    tabParam === 'users' || tabParam === 'roles' ? tabParam : 'overview'
  const setTab = (tab: WorkspaceTab) =>
    setSearchParams(tab === 'overview' ? {} : { tab }, { replace: true })

  const toggleStatus = async () => {
    if (!store) return
    setStatusBusy(true)
    setStatusError(null)
    try {
      await storeService.setStatus(store.store_id, !store.is_active)
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
        <PageHeader title="Store" breadcrumb={['Platform', 'Stores', '…']} />
        <TableSkeleton rows={4} columns={2} />
      </div>
    )
  }

  if (error || !store) {
    return (
      <div className="container-fluid px-0">
        <PageHeader title="Store" breadcrumb={['Platform', 'Stores', 'Not found']} />
        <ErrorState
          title="Store unavailable"
          description={error ?? 'This store could not be found.'}
          onRetry={reload}
        />
        <div className="text-center mt-3">
          <Link to="/platform/stores" className="btn btn-link">
            Back to Stores
          </Link>
        </div>
      </div>
    )
  }

  const tenantName = tenant?.tenant_name ?? '—'

  return (
    <div className="container-fluid px-0">
      <div className="workspace-header">
        <div className="workspace-header__info">
          <nav aria-label="breadcrumb">
            <ol className="breadcrumb small mb-2">
              <li className="breadcrumb-item">Platform</li>
              <li className="breadcrumb-item">
                <Link to="/platform/stores">Stores</Link>
              </li>
              <li className="breadcrumb-item active" aria-current="page">
                {store.store_name}
              </li>
            </ol>
          </nav>
          <div className="workspace-header__title">
            <h1 className="h3 mb-0">{store.store_name}</h1>
            <StatusBadge active={store.is_active} />
          </div>
          <div className="workspace-stats">
            <span className="workspace-stat">
              <i className="bi bi-building" aria-hidden="true" />
              <span className="workspace-stat__value">{tenantName}</span>
              <span>Tenant</span>
            </span>
            <span className="workspace-stat" title="User counts are not available yet">
              <i className="bi bi-people" aria-hidden="true" />
              <strong className="workspace-stat__value" aria-label="User count not available">
                —
              </strong>
              <span>Users</span>
            </span>
            <span className="workspace-stat" title="Role counts are not available yet">
              <i className="bi bi-person-badge" aria-hidden="true" />
              <strong className="workspace-stat__value" aria-label="Role count not available">
                —
              </strong>
              <span>Roles</span>
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
            className={`btn ${store.is_active ? 'btn-outline-danger' : 'btn-outline-success'}`}
            onClick={toggleStatus}
            disabled={statusBusy}
          >
            {statusBusy ? (
              <span className="spinner-border spinner-border-sm me-1" aria-hidden="true" />
            ) : (
              <i
                className={`bi ${store.is_active ? 'bi-pause-circle' : 'bi-play-circle'} me-1`}
                aria-hidden="true"
              />
            )}
            {store.is_active ? 'Deactivate' : 'Activate'}
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
                <dt className="col-sm-3">Store Code</dt>
                <dd className="col-sm-9">{store.store_code}</dd>
                <dt className="col-sm-3">Store Name</dt>
                <dd className="col-sm-9">{store.store_name}</dd>
                <dt className="col-sm-3">Tenant</dt>
                <dd className="col-sm-9">{tenantName}</dd>
                <dt className="col-sm-3">Server Name</dt>
                <dd className="col-sm-9">{store.server_name}</dd>
                <dt className="col-sm-3">Database Name</dt>
                <dd className="col-sm-9">
                  <code>{store.database_name}</code>
                </dd>
                <dt className="col-sm-3">Status</dt>
                <dd className="col-sm-9">
                  <StatusBadge active={store.is_active} />
                </dd>
              </dl>
            </div>
          </div>
        )}

        {activeTab === 'users' && (
          <EmptyState
            icon="bi-people"
            title="No Users Found"
            description="Assign users to this store to see them here."
            action={{
              label: 'Create User',
              icon: 'bi-person-plus',
              onClick: () => navigate('/platform/users'),
            }}
          />
        )}

        {activeTab === 'roles' && (
          <EmptyState
            icon="bi-person-badge"
            title="No Roles Found"
            description="Assign roles to this store to see them here."
            action={{
              label: 'Create Role',
              icon: 'bi-plus-lg',
              onClick: () => navigate('/platform/roles'),
            }}
          />
        )}
      </div>

      {editing && (
        <StoreFormModal
          mode="edit"
          store={store}
          tenants={tenants}
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
