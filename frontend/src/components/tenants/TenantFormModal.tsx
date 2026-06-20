import { useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import type { Tenant, TenantInput } from '../../types/tenant'
import { tenantService } from '../../services/tenantService'

interface TenantFormModalProps {
  mode: 'create' | 'edit'
  tenant?: Tenant
  onClose: () => void
  onSaved: () => void
}

const EMPTY_FORM: TenantInput = {
  tenant_code: '',
  tenant_abbreviation: '',
  tenant_name: '',
  db_name: '',
}

export function TenantFormModal({ mode, tenant, onClose, onSaved }: TenantFormModalProps) {
  const [form, setForm] = useState<TenantInput>(() =>
    tenant
      ? {
          tenant_code: tenant.tenant_code,
          tenant_abbreviation: tenant.tenant_abbreviation,
          tenant_name: tenant.tenant_name,
          db_name: tenant.db_name,
        }
      : EMPTY_FORM,
  )
  const [validated, setValidated] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const updateField =
    (key: keyof TenantInput) => (event: ChangeEvent<HTMLInputElement>) =>
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
        await tenantService.create(form)
      } else if (tenant) {
        await tenantService.update(tenant.tenant_id, form)
      }
      onSaved()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save tenant')
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
                <h5 className="modal-title">
                  {mode === 'create' ? 'Add Tenant' : 'Edit Tenant'}
                </h5>
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
                  <label htmlFor="tenant-code" className="form-label">
                    Tenant Code
                  </label>
                  <input
                    id="tenant-code"
                    className="form-control"
                    required
                    value={form.tenant_code}
                    onChange={updateField('tenant_code')}
                  />
                  <div className="invalid-feedback">Tenant code is required.</div>
                </div>
                <div>
                  <label htmlFor="tenant-abbreviation" className="form-label">
                    Tenant Abbreviation
                  </label>
                  <input
                    id="tenant-abbreviation"
                    className="form-control"
                    required
                    value={form.tenant_abbreviation}
                    onChange={updateField('tenant_abbreviation')}
                  />
                  <div className="invalid-feedback">Abbreviation is required.</div>
                </div>
                <div>
                  <label htmlFor="tenant-name" className="form-label">
                    Tenant Name
                  </label>
                  <input
                    id="tenant-name"
                    className="form-control"
                    required
                    value={form.tenant_name}
                    onChange={updateField('tenant_name')}
                  />
                  <div className="invalid-feedback">Tenant name is required.</div>
                </div>
                <div>
                  <label htmlFor="tenant-db" className="form-label">
                    Database Name
                  </label>
                  <input
                    id="tenant-db"
                    className="form-control"
                    required
                    value={form.db_name}
                    onChange={updateField('db_name')}
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
