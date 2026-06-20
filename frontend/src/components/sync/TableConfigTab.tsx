import { useState } from 'react'
import { useAsyncData } from '../../hooks/useAsyncData'
import { syncService } from '../../services/syncService'
import { EmptyState } from '../common/EmptyState'
import { ErrorState } from '../common/ErrorState'
import { TableSkeleton } from '../common/TableSkeleton'
import { SyncTableFormModal } from './SyncTableFormModal'
import type { SyncTable } from '../../types/sync'

type ModalState = { mode: 'create' } | { mode: 'edit'; table: SyncTable } | null

export function TableConfigTab() {
  const { data, isLoading, error, reload } = useAsyncData(syncService.tables)
  const [modal, setModal] = useState<ModalState>(null)
  const [togglingId, setTogglingId] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  const toggleEnabled = async (table: SyncTable) => {
    setTogglingId(table.sync_table_id)
    setActionError(null)
    try {
      await syncService.setTableStatus(table.sync_table_id, !table.is_active)
      await reload()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to update table')
    } finally {
      setTogglingId(null)
    }
  }

  const renderBody = () => {
    if (isLoading) return <TableSkeleton rows={5} columns={6} />
    if (error || !data) return <ErrorState description={error ?? 'Failed to load tables'} onRetry={reload} />
    if (data.length === 0) {
      return (
        <EmptyState
          icon="bi-table"
          title="No tables configured"
          description="Add a discovered table from the schema catalog to start configuring sync."
          action={{ label: 'Add Table', icon: 'bi-plus-lg', onClick: () => setModal({ mode: 'create' }) }}
        />
      )
    }
    return (
      <div className="table-responsive">
        <table className="table table-hover align-middle data-table">
          <thead>
            <tr>
              <th scope="col">Enabled</th>
              <th scope="col">Table Name</th>
              <th scope="col">Sync Mode</th>
              <th scope="col">Watermark Column</th>
              <th scope="col">Window Days</th>
              <th scope="col">Custom Where</th>
              <th scope="col">Sync Order</th>
              <th scope="col" className="text-end">Actions</th>
            </tr>
          </thead>
          <tbody>
            {data.map((table) => (
              <tr key={table.sync_table_id}>
                <td>
                  <button
                    type="button"
                    className={`btn btn-sm ${table.is_active ? 'btn-success' : 'btn-outline-secondary'}`}
                    aria-pressed={table.is_active}
                    aria-label={`${table.is_active ? 'Disable' : 'Enable'} ${table.table_name}`}
                    disabled={togglingId === table.sync_table_id}
                    onClick={() => toggleEnabled(table)}
                  >
                    {togglingId === table.sync_table_id ? (
                      <span className="spinner-border spinner-border-sm" aria-hidden="true" />
                    ) : (
                      <i className={`bi ${table.is_active ? 'bi-check-lg' : 'bi-x-lg'}`} aria-hidden="true" />
                    )}
                  </button>
                </td>
                <td className="fw-medium">{table.table_name}</td>
                <td><span className="badge text-bg-secondary">{table.sync_mode}</span></td>
                <td>{table.watermark_column ?? '—'}</td>
                <td>{table.window_days ?? '—'}</td>
                <td className="text-secondary">{table.custom_where ?? '—'}</td>
                <td>{table.sync_order}</td>
                <td className="text-end">
                  <button
                    type="button"
                    className="btn btn-sm btn-outline-secondary"
                    title="Edit"
                    aria-label={`Edit ${table.table_name}`}
                    onClick={() => setModal({ mode: 'edit', table })}
                  >
                    <i className="bi bi-pencil" aria-hidden="true" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  return (
    <div>
      <div className="d-flex justify-content-end mb-3">
        <button type="button" className="btn btn-primary" onClick={() => setModal({ mode: 'create' })}>
          <i className="bi bi-plus-lg me-1" aria-hidden="true" />
          Add Table
        </button>
      </div>
      {actionError && <div className="alert alert-danger py-2">{actionError}</div>}
      {renderBody()}
      {modal && (
        <SyncTableFormModal
          mode={modal.mode}
          table={modal.mode === 'edit' ? modal.table : undefined}
          onClose={() => setModal(null)}
          onSaved={() => {
            setModal(null)
            void reload()
          }}
        />
      )}
    </div>
  )
}
