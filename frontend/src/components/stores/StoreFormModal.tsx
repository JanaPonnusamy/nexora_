import { useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import type { Store, StoreInput } from '../../types/store'
import type { Tenant } from '../../types/tenant'
import { storeService } from '../../services/storeService'

interface StoreFormModalProps {
  mode: 'create' | 'edit'
  store?: Store
  tenants: Tenant[]
  onClose: () => void
  onSaved: () => void
}

const EMPTY_FORM: StoreInput = {
  tenant_id: '',
  store_code: '',
  store_name: '',
  server_name: '',
  database_name: '',
}

export function StoreFormModal({ mode, store, tenants, onClose, onSaved }: StoreFormModalProps) {
  const [form, setForm] = useState<StoreInput>(() =>
    store
      ? {
          tenant_id: store.tenant_id,
          store_code: store.store_code,
          store_name: store.store_name,
          server_name: store.server_name,
          database_name: store.database_name,
        }
      : EMPTY_FORM,
  )
  const [validated, setValidated] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const updateField =
    (key: keyof StoreInput) =>
    (event: ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
      setForm((current) => ({ ...current, [key]: event.target.value }))

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!event.currentTarget.checkValidity()) {
      setValidated(true)
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      if (mode === 'create') {
        await storeService.create(form)
      } else if (store) {
        await storeService.update(store.store_id, form)
      }
      onSaved()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save store')
      setSubmitting(false)
    }
  }

  return (
    <>
      <div className="modal fade show d-block" tabIndex={-1} role="dialog">
        <div className="modal-dialog modal-dialog-centered">
          <div className="modal-content">
            <form
              className={`needs-validation${validated ? ' was-validated' : ''}`}
              noValidate
              onSubmit={handleSubmit}
            >
              <div className="modal-header">
                <h5 className="modal-title">{mode === 'create' ? 'Add Store' : 'Edit Store'}</h5>
                <button
                  type="button"
                  className="btn-close"
                  aria-label="Close"
                  onClick={onClose}
                  disabled={submitting}
                />
              </div>
              <div className="modal-body vstack gap-3">
                {error && <div className="alert alert-danger py-2 mb-0">{error}</div>}
                <div>
                  <label htmlFor="store-tenant" className="form-label">
                    Tenant
                  </label>
                  <select
                    id="store-tenant"
                    className="form-select"
                    required
                    value={form.tenant_id}
                    onChange={updateField('tenant_id')}
                  >
                    <option value="" disabled>
                      Select a tenant
                    </option>
                    {tenants.map((tenant) => (
                      <option key={tenant.tenant_id} value={tenant.tenant_id}>
                        {tenant.tenant_name}
                      </option>
                    ))}
                  </select>
                  <div className="invalid-feedback">Tenant is required.</div>
                </div>
                <div>
                  <label htmlFor="store-code" className="form-label">
                    Store Code
                  </label>
                  <input
                    id="store-code"
                    className="form-control"
                    required
                    value={form.store_code}
                    onChange={updateField('store_code')}
                  />
                  <div className="invalid-feedback">Store code is required.</div>
                </div>
                <div>
                  <label htmlFor="store-name" className="form-label">
                    Store Name
                  </label>
                  <input
                    id="store-name"
                    className="form-control"
                    required
                    value={form.store_name}
                    onChange={updateField('store_name')}
                  />
                  <div className="invalid-feedback">Store name is required.</div>
                </div>
                <div>
                  <label htmlFor="store-server" className="form-label">
                    Server Name
                  </label>
                  <input
                    id="store-server"
                    className="form-control"
                    required
                    value={form.server_name}
                    onChange={updateField('server_name')}
                  />
                  <div className="invalid-feedback">Server name is required.</div>
                </div>
                <div>
                  <label htmlFor="store-db" className="form-label">
                    Database Name
                  </label>
                  <input
                    id="store-db"
                    className="form-control"
                    required
                    value={form.database_name}
                    onChange={updateField('database_name')}
                  />
                  <div className="invalid-feedback">Database name is required.</div>
                </div>
              </div>
              <div className="modal-footer">
                <button
                  type="button"
                  className="btn btn-link"
                  onClick={onClose}
                  disabled={submitting}
                >
                  Cancel
                </button>
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
