import { useEffect, useState } from 'react'
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
import type { StoreCredentials } from '../../types/store'

type WorkspaceTab = 'overview' | 'connection' | 'users' | 'roles'

const TABS: { key: WorkspaceTab; label: string; icon: string }[] = [
  { key: 'overview', label: 'Overview', icon: 'bi-info-circle' },
  { key: 'connection', label: 'Connection', icon: 'bi-hdd-network' },
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
    tabParam === 'users' || tabParam === 'roles' || tabParam === 'connection'
      ? tabParam
      : 'overview'
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

        {activeTab === 'connection' && <StoreConnectionTab storeId={store.store_id} />}

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

/** DB connection editor — the HO UI for a store's server/database/username/
 *  password/connection type. Replaces the manual UPDATE dbo.stores step; the
 *  password is encrypted server-side and never returned (leave blank to keep
 *  the existing one). Super-admin only (the endpoint 403s otherwise). */
function StoreConnectionTab({ storeId }: { storeId: string }) {
  const [creds, setCreds] = useState<StoreCredentials | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [busy, setBusy] = useState(false)
  const [server, setServer] = useState('')
  const [database, setDatabase] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [connType, setConnType] = useState('')

  useEffect(() => {
    let live = true
    setLoading(true)
    setError(null)
    storeService
      .getCredentials(storeId)
      .then((c) => {
        if (!live) return
        setCreds(c)
        setServer(c.server_name ?? '')
        setDatabase(c.database_name ?? '')
        setUsername(c.username ?? '')
        setConnType(c.connection_type ?? '')
      })
      .catch((e) => live && setError(e instanceof Error ? e.message : 'Failed to load'))
      .finally(() => live && setLoading(false))
    return () => {
      live = false
    }
  }, [storeId])

  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    setSaved(false)
    try {
      const updated = await storeService.updateCredentials(storeId, {
        server_name: server,
        database_name: database,
        username,
        password: password || null,
        connection_type: connType,
      })
      setCreds(updated)
      setPassword('')
      setSaved(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save')
    } finally {
      setBusy(false)
    }
  }

  if (loading) {
    return <div className="card"><div className="card-body text-muted">Loading connection…</div></div>
  }

  return (
    <div className="card">
      <div className="card-body">
        <p className="text-muted small">
          The store agent fetches these credentials from HO and re-confirms them every sync — a
          change here is picked up automatically, no visit to the store machine.
        </p>
        {error && <div className="alert alert-danger py-2">{error}</div>}
        {saved && <div className="alert alert-success py-2">Connection saved.</div>}
        <form className="row g-3" onSubmit={save} style={{ maxWidth: 640 }}>
          <div className="col-md-6">
            <label className="form-label">Server Name</label>
            <input className="form-control" value={server} onChange={(e) => setServer(e.target.value)} placeholder="HOST\\SQLEXPRESS" />
          </div>
          <div className="col-md-6">
            <label className="form-label">Database Name</label>
            <input className="form-control" value={database} onChange={(e) => setDatabase(e.target.value)} placeholder="shopaid" />
          </div>
          <div className="col-md-6">
            <label className="form-label">Username</label>
            <input className="form-control" value={username} onChange={(e) => setUsername(e.target.value)} placeholder="sa" autoComplete="off" />
          </div>
          <div className="col-md-6">
            <label className="form-label">
              Password{' '}
              <span className="text-muted small">
                {creds?.has_password ? '(set — leave blank to keep)' : '(not set)'}
              </span>
            </label>
            <input
              type="password"
              className="form-control"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={creds?.has_password ? '••••••••' : 'Enter password'}
              autoComplete="new-password"
            />
          </div>
          <div className="col-md-6">
            <label className="form-label">Connection Type</label>
            <input className="form-control" value={connType} onChange={(e) => setConnType(e.target.value)} placeholder="LAN / R / SQL" />
          </div>
          <div className="col-12">
            <button type="submit" className="btn btn-primary" disabled={busy}>
              {busy && <span className="spinner-border spinner-border-sm me-1" aria-hidden="true" />}
              Save connection
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
