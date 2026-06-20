import { useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import type { CatalogTable, SyncTable, SyncTableInput } from '../../types/sync'
import { syncService } from '../../services/syncService'

interface SyncTableFormModalProps {
  mode: 'create' | 'edit'
  table?: SyncTable
  onClose: () => void
  onSaved: () => void
}

interface FormState {
  table_name: string
  sync_mode: string
  watermark_column: string
  window_days: string
  custom_where: string
  sync_order: string
}

export function SyncTableFormModal({ mode, table, onClose, onSaved }: SyncTableFormModalProps) {
  const [form, setForm] = useState<FormState>(() => ({
    table_name: table?.table_name ?? '',
    sync_mode: table?.sync_mode ?? 'UPSERT',
    watermark_column: table?.watermark_column ?? '',
    window_days: table?.window_days != null ? String(table.window_days) : '',
    custom_where: table?.custom_where ?? '',
    sync_order: table?.sync_order != null ? String(table.sync_order) : '0',
  }))
  const [catalogSearch, setCatalogSearch] = useState('')
  const [catalogResults, setCatalogResults] = useState<CatalogTable[]>([])
  const [catalogLoading, setCatalogLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const isRolling = form.sync_mode === 'ROLLING_WINDOW'

  const update =
    (key: keyof FormState) =>
    (event: ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
      setForm((current) => ({ ...current, [key]: event.target.value }))

  const searchCatalog = async () => {
    setCatalogLoading(true)
    setError(null)
    try {
      setCatalogResults(await syncService.catalogTables(catalogSearch.trim()))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to search catalog')
    } finally {
      setCatalogLoading(false)
    }
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!form.table_name.trim()) {
      setError('Select a table from the catalog')
      return
    }
    if (isRolling && (!form.watermark_column.trim() || form.window_days.trim() === '')) {
      setError('Watermark column and window days are required for ROLLING_WINDOW')
      return
    }

    const input: SyncTableInput = {
      table_name: form.table_name.trim(),
      sync_mode: form.sync_mode,
      watermark_column: isRolling ? form.watermark_column.trim() || null : null,
      window_days: isRolling ? Number(form.window_days) : null,
      custom_where: form.custom_where.trim() || null,
      sync_order: Number(form.sync_order) || 0,
      is_active: table?.is_active ?? true,
    }

    setSubmitting(true)
    setError(null)
    try {
      if (mode === 'create') {
        await syncService.createTable(input)
      } else if (table) {
        await syncService.updateTable(table.sync_table_id, input)
      }
      onSaved()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save table')
      setSubmitting(false)
    }
  }

  return (
    <>
      <div className="modal fade show d-block" tabIndex={-1} role="dialog">
        <div className="modal-dialog modal-dialog-centered modal-lg">
          <div className="modal-content">
            <form onSubmit={handleSubmit}>
              <div className="modal-header">
                <h5 className="modal-title">{mode === 'create' ? 'Add Sync Table' : 'Edit Sync Table'}</h5>
                <button type="button" className="btn-close" aria-label="Close" onClick={onClose} disabled={submitting} />
              </div>
              <div className="modal-body vstack gap-3">
                {error && <div className="alert alert-danger py-2 mb-0">{error}</div>}

                {mode === 'create' && (
                  <div>
                    <label className="form-label">Catalog Table</label>
                    <div className="input-group">
                      <input
                        type="search"
                        className="form-control"
                        placeholder="Search discovered tables"
                        aria-label="Search catalog tables"
                        value={catalogSearch}
                        onChange={(e) => setCatalogSearch(e.target.value)}
                      />
                      <button type="button" className="btn btn-outline-secondary" onClick={searchCatalog} disabled={catalogLoading}>
                        {catalogLoading ? (
                          <span className="spinner-border spinner-border-sm" aria-hidden="true" />
                        ) : (
                          <i className="bi bi-search" aria-hidden="true" />
                        )}
                      </button>
                    </div>
                    {catalogResults.length > 0 && (
                      <ul className="list-group mt-2 sync-catalog-list">
                        {catalogResults.map((item) => (
                          <li key={`${item.schema_name}.${item.table_name}`} className="list-group-item p-0">
                            <button
                              type="button"
                              className={`btn btn-sm w-100 text-start ${form.table_name === item.table_name ? 'btn-primary' : 'btn-link'}`}
                              onClick={() => setForm((c) => ({ ...c, table_name: item.table_name }))}
                            >
                              {item.schema_name}.{item.table_name}
                            </button>
                          </li>
                        ))}
                      </ul>
                    )}
                    <div className="form-text">Selected: {form.table_name || '—'} (tables cannot be typed manually)</div>
                  </div>
                )}

                <div className="row g-3">
                  <div className="col-md-6">
                    <label htmlFor="sync-mode" className="form-label">Sync Mode</label>
                    <select id="sync-mode" className="form-select" value={form.sync_mode} onChange={update('sync_mode')}>
                      <option value="UPSERT">UPSERT</option>
                      <option value="ROLLING_WINDOW">ROLLING_WINDOW</option>
                    </select>
                  </div>
                  <div className="col-md-6">
                    <label htmlFor="sync-order" className="form-label">Sync Order</label>
                    <input id="sync-order" type="number" className="form-control" value={form.sync_order} onChange={update('sync_order')} />
                  </div>
                  <div className="col-md-6">
                    <label htmlFor="watermark" className="form-label">Watermark Column</label>
                    <input id="watermark" className="form-control" value={form.watermark_column} onChange={update('watermark_column')} disabled={!isRolling} placeholder={isRolling ? '' : 'Not used for UPSERT'} />
                  </div>
                  <div className="col-md-6">
                    <label htmlFor="window-days" className="form-label">Window Days</label>
                    <input id="window-days" type="number" className="form-control" value={form.window_days} onChange={update('window_days')} disabled={!isRolling} placeholder={isRolling ? '' : 'Not used for UPSERT'} />
                  </div>
                  <div className="col-12">
                    <label htmlFor="custom-where" className="form-label">Custom Where</label>
                    <textarea id="custom-where" className="form-control" rows={2} value={form.custom_where} onChange={update('custom_where')} />
                  </div>
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-link" onClick={onClose} disabled={submitting}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={submitting}>
                  {submitting ? (
                    <>
                      <span className="spinner-border spinner-border-sm me-2" aria-hidden="true" />
                      Saving…
                    </>
                  ) : (
                    'Save'
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      </div>
      <div className="modal-backdrop fade show" />
    </>
  )
}
