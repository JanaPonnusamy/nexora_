import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { PageHeader } from '../../components/common/PageHeader'
import { ErrorState } from '../../components/common/ErrorState'
import { TableSkeleton } from '../../components/common/TableSkeleton'
import { StatusBadge } from '../../components/common/StatusBadge'
import { ModuleFormModal } from '../../components/modules/ModuleFormModal'
import { useModule } from '../../hooks/useModule'
import { moduleService } from '../../services/moduleService'

export default function ModuleWorkspacePage() {
  const { moduleId } = useParams<{ moduleId: string }>()
  const { module, isLoading, error, reload } = useModule(moduleId)
  const [editing, setEditing] = useState(false)
  const [statusBusy, setStatusBusy] = useState(false)
  const [statusError, setStatusError] = useState<string | null>(null)

  const toggleStatus = async () => {
    if (!module) return
    setStatusBusy(true)
    setStatusError(null)
    try {
      await moduleService.setStatus(module.module_id, !module.is_active)
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
        <PageHeader title="Module" breadcrumb={['Administration', 'Modules', '…']} />
        <TableSkeleton rows={4} columns={2} />
      </div>
    )
  }

  if (error || !module) {
    return (
      <div className="container-fluid px-0">
        <PageHeader title="Module" breadcrumb={['Administration', 'Modules', 'Not found']} />
        <ErrorState
          title="Module unavailable"
          description={error ?? 'This module could not be found.'}
          onRetry={reload}
        />
        <div className="text-center mt-3">
          <Link to="/administration/modules" className="btn btn-link">
            Back to Modules
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
              <li className="breadcrumb-item">Administration</li>
              <li className="breadcrumb-item">
                <Link to="/administration/modules">Modules</Link>
              </li>
              <li className="breadcrumb-item active" aria-current="page">
                {module.module_name}
              </li>
            </ol>
          </nav>
          <div className="workspace-header__title">
            <h1 className="h3 mb-0">{module.module_name}</h1>
            <StatusBadge active={module.is_active} />
          </div>
          <div className="workspace-stats">
            <span className="workspace-stat">
              <i className="bi bi-upc-scan" aria-hidden="true" />
              <strong className="workspace-stat__value">{module.module_code}</strong>
              <span>Module Code</span>
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
            className={`btn ${module.is_active ? 'btn-outline-danger' : 'btn-outline-success'}`}
            onClick={toggleStatus}
            disabled={statusBusy}
          >
            {statusBusy ? (
              <span className="spinner-border spinner-border-sm me-1" aria-hidden="true" />
            ) : (
              <i
                className={`bi ${module.is_active ? 'bi-pause-circle' : 'bi-play-circle'} me-1`}
                aria-hidden="true"
              />
            )}
            {module.is_active ? 'Deactivate' : 'Activate'}
          </button>
        </div>
      </div>

      {statusError && <div className="alert alert-danger py-2">{statusError}</div>}

      <ul className="nav nav-tabs mb-3" role="tablist">
        <li className="nav-item" role="presentation">
          <button
            type="button"
            role="tab"
            id="tab-overview"
            aria-selected={true}
            aria-controls="panel-overview"
            className="nav-link active"
          >
            <i className="bi bi-info-circle me-1" aria-hidden="true" />
            Overview
          </button>
        </li>
      </ul>

      <div role="tabpanel" id="panel-overview" aria-labelledby="tab-overview">
        <div className="card">
          <div className="card-body">
            <dl className="row mb-0 workspace-details">
              <dt className="col-sm-3">Module Code</dt>
              <dd className="col-sm-9">
                <code>{module.module_code}</code>
              </dd>
              <dt className="col-sm-3">Module Name</dt>
              <dd className="col-sm-9">{module.module_name}</dd>
              <dt className="col-sm-3">Description</dt>
              <dd className="col-sm-9">{module.description ?? '—'}</dd>
              <dt className="col-sm-3">Status</dt>
              <dd className="col-sm-9">
                <StatusBadge active={module.is_active} />
              </dd>
            </dl>
          </div>
        </div>
      </div>

      {editing && (
        <ModuleFormModal
          mode="edit"
          module={module}
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
