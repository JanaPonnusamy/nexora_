import { useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import type { Module, ModuleInput } from '../../types/module'
import { moduleService } from '../../services/moduleService'

interface ModuleFormModalProps {
  mode: 'create' | 'edit'
  module?: Module
  onClose: () => void
  onSaved: () => void
}

const EMPTY_FORM: ModuleInput = {
  module_code: '',
  module_name: '',
  description: '',
}

export function ModuleFormModal({ mode, module, onClose, onSaved }: ModuleFormModalProps) {
  const [form, setForm] = useState<ModuleInput>(() =>
    module
      ? {
          module_code: module.module_code,
          module_name: module.module_name,
          description: module.description ?? '',
        }
      : EMPTY_FORM,
  )
  const [validated, setValidated] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const updateField =
    (key: keyof ModuleInput) =>
    (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
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
        await moduleService.create(form)
      } else if (module) {
        await moduleService.update(module.module_id, form)
      }
      onSaved()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save module')
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
                <h5 className="modal-title">{mode === 'create' ? 'Add Module' : 'Edit Module'}</h5>
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
                  <label htmlFor="module-code" className="form-label">
                    Module Code
                  </label>
                  <input
                    id="module-code"
                    className="form-control"
                    required
                    value={form.module_code}
                    onChange={updateField('module_code')}
                  />
                  <div className="invalid-feedback">Module code is required.</div>
                </div>
                <div>
                  <label htmlFor="module-name" className="form-label">
                    Module Name
                  </label>
                  <input
                    id="module-name"
                    className="form-control"
                    required
                    value={form.module_name}
                    onChange={updateField('module_name')}
                  />
                  <div className="invalid-feedback">Module name is required.</div>
                </div>
                <div>
                  <label htmlFor="module-description" className="form-label">
                    Description
                  </label>
                  <textarea
                    id="module-description"
                    className="form-control"
                    rows={3}
                    value={form.description}
                    onChange={updateField('description')}
                  />
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
