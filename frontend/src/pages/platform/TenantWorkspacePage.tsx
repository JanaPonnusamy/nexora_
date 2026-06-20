import { useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { PageHeader } from '../../components/common/PageHeader'
import { EmptyState } from '../../components/common/EmptyState'
import { ErrorState } from '../../components/common/ErrorState'
import { TableSkeleton } from '../../components/common/TableSkeleton'
import { StatusBadge } from '../../components/common/StatusBadge'
import { Skeleton } from '../../components/common/Skeleton'
import { TenantStores } from '../../components/tenants/TenantStores'
import { TenantFormModal } from '../../components/tenants/TenantFormModal'
import { tenantAccent } from '../../components/tenants/tenantAccent'
import { useTenant } from '../../hooks/useTenant'
import { useTenantStores } from '../../hooks/useTenantStores'
import { tenantService } from '../../services/tenantService'

type WorkspaceTab = 'overview' | 'stores' | 'users'

const TABS: { key: WorkspaceTab; label: string; icon: string }[] = [
  { key: 'overview', label: 'Overview', icon: 'bi-info-circle' },
  { key: 'stores', label: 'Stores', icon: 'bi-shop' },
  { key: 'users', label: 'Users', icon: 'bi-people' },
]

export default function TenantWorkspacePage() {
  const { tenantId } = useParams<{ tenantId: string }>()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const { tenant, isLoading, error, reload } = useTenant(tenantId)
  const {
    stores,
    isLoading: storesLoading,
    error: storesError,
    reload: reloadStores,
  } = useTenantStores(tenantId)
  const [editing, setEditing] = useState(false)
  const [statusBusy, setStatusBusy] = useState(false)
  const [statusError, setStatusError] = useState<string | null>(null)

  const tabParam = searchParams.get('tab')
  const activeTab: WorkspaceTab =
    tabParam === 'stores' || tabParam === 'users' ? tabParam : 'overview'
  const setTab = (tab: WorkspaceTab) =>
    setSearchParams(tab === 'overview' ? {} : { tab }, { replace: true })

  const toggleStatus = async () => {
    if (!tenant) return
    setStatusBusy(true)
    setStatusError(null)
    try {
      await tenantService.setStatus(tenant.tenant_id, !tenant.is_active)
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
        <PageHeader title="Tenant" breadcrumb={['Platform', 'Tenants', '…']} />
        <TableSkeleton rows={4} columns={2} />
      </div>
    )
  }

  if (error || !tenant) {
    return (
      <div className="container-fluid px-0">
        <PageHeader title="Tenant" breadcrumb={['Platform', 'Tenants', 'Not found']} />
        <ErrorState
          title="Tenant unavailable"
          description={error ?? 'This tenant could not be found.'}
          onRetry={reload}
        />
        <div className="text-center mt-3">
          <Link to="/platform/tenants" className="btn btn-link">
            Back to Tenants
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
                <Link to="/platform/tenants">Tenants</Link>
              </li>
              <li className="breadcrumb-item active" aria-current="page">
                {tenant.tenant_name}
              </li>
            </ol>
          </nav>
          <div className="workspace-header__title">
            <span className={`tenant-avatar tenant-avatar--${tenantAccent(tenant.tenant_code)}`}>
              <i className="bi bi-building" aria-hidden="true" />
            </span>
            <h1 className="h3 mb-0">{tenant.tenant_name}</h1>
            <StatusBadge active={tenant.is_active} />
          </div>
          <div className="workspace-stats">
            <span className="workspace-stat">
              <i className="bi bi-shop" aria-hidden="true" />
              {storesLoading ? (
                <Skeleton width="1.5rem" height="0.9rem" />
              ) : (
                <strong className="workspace-stat__value">
                  {storesError ? '—' : stores.length}
                </strong>
              )}
              <span>Stores</span>
            </span>
            <span className="workspace-stat" title="User counts are not available yet">
              <i className="bi bi-people" aria-hidden="true" />
              <strong className="workspace-stat__value" aria-label="User count not available">
                —
              </strong>
              <span>Users</span>
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
            className={`btn ${tenant.is_active ? 'btn-outline-danger' : 'btn-outline-success'}`}
            onClick={toggleStatus}
            disabled={statusBusy}
          >
            {statusBusy ? (
              <span className="spinner-border spinner-border-sm me-1" aria-hidden="true" />
            ) : (
              <i
                className={`bi ${tenant.is_active ? 'bi-pause-circle' : 'bi-play-circle'} me-1`}
                aria-hidden="true"
              />
            )}
            {tenant.is_active ? 'Deactivate' : 'Activate'}
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
                <dt className="col-sm-3">Tenant Code</dt>
                <dd className="col-sm-9">{tenant.tenant_code}</dd>
                <dt className="col-sm-3">Abbreviation</dt>
                <dd className="col-sm-9">{tenant.tenant_abbreviation}</dd>
                <dt className="col-sm-3">Tenant Name</dt>
                <dd className="col-sm-9">{tenant.tenant_name}</dd>
                <dt className="col-sm-3">Database Name</dt>
                <dd className="col-sm-9">
                  <code>{tenant.db_name}</code>
                </dd>
                <dt className="col-sm-3">Status</dt>
                <dd className="col-sm-9">
                  <StatusBadge active={tenant.is_active} />
                </dd>
              </dl>
            </div>
          </div>
        )}

        {activeTab === 'stores' && (
          <TenantStores
            stores={stores}
            isLoading={storesLoading}
            error={storesError}
            onRetry={reloadStores}
            onCreateStore={() => navigate('/platform/stores')}
          />
        )}

        {activeTab === 'users' && (
          <EmptyState
            icon="bi-people"
            title="No Users Found"
            description="Assign users to this tenant to see them here."
            action={{
              label: 'Create User',
              icon: 'bi-person-plus',
              onClick: () => navigate('/platform/users'),
            }}
          />
        )}
      </div>

      {editing && (
        <TenantFormModal
          mode="edit"
          tenant={tenant}
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
