import { useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import type { Role, RoleInput } from '../../types/role'
import { roleService } from '../../services/roleService'

interface RoleFormModalProps {
  mode: 'create' | 'edit'
  role?: Role
  onClose: () => void
  onSaved: () => void
}

const EMPTY_FORM: RoleInput = {
  role_name: '',
  description: '',
}

export function RoleFormModal({ mode, role, onClose, onSaved }: RoleFormModalProps) {
  const [form, setForm] = useState<RoleInput>(() =>
    role ? { role_name: role.role_name, description: role.description ?? '' } : EMPTY_FORM,
  )
  const [validated, setValidated] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const updateField =
    (key: keyof RoleInput) =>
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
        await roleService.create(form)
      } else if (role) {
        await roleService.update(role.role_id, form)
      }
      onSaved()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save role')
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
                <h5 className="modal-title">{mode === 'create' ? 'Add Role' : 'Edit Role'}</h5>
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
                  <label htmlFor="role-name" className="form-label">
                    Role Name
                  </label>
                  <input
                    id="role-name"
                    className="form-control"
                    required
                    value={form.role_name}
                    onChange={updateField('role_name')}
                  />
                  <div className="invalid-feedback">Role name is required.</div>
                </div>
                <div>
                  <label htmlFor="role-description" className="form-label">
                    Description
                  </label>
                  <textarea
                    id="role-description"
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
