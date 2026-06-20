import { useState } from 'react'
import type { ChangeEvent, FormEvent } from 'react'
import type { User, UserInput } from '../../types/user'
import { userService } from '../../services/userService'

interface UserFormModalProps {
  mode: 'create' | 'edit'
  user?: User
  onClose: () => void
  onSaved: () => void
}

const EMPTY_FORM: UserInput = {
  username: '',
  full_name: '',
  password: '',
}

export function UserFormModal({ mode, user, onClose, onSaved }: UserFormModalProps) {
  const [form, setForm] = useState<UserInput>(() =>
    user
      ? { username: user.username, full_name: user.full_name }
      : EMPTY_FORM,
  )
  const [validated, setValidated] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const updateField =
    (key: keyof UserInput) => (event: ChangeEvent<HTMLInputElement>) =>
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
        await userService.create(form)
      } else if (user) {
        await userService.update(user.user_id, {
          username: form.username,
          full_name: form.full_name,
        })
      }
      onSaved()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save user')
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
                <h5 className="modal-title">{mode === 'create' ? 'Add User' : 'Edit User'}</h5>
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
                  <label htmlFor="user-username" className="form-label">
                    Username
                  </label>
                  <input
                    id="user-username"
                    className="form-control"
                    required
                    value={form.username}
                    onChange={updateField('username')}
                  />
                  <div className="invalid-feedback">Username is required.</div>
                </div>
                <div>
                  <label htmlFor="user-fullname" className="form-label">
                    Full Name
                  </label>
                  <input
                    id="user-fullname"
                    className="form-control"
                    required
                    value={form.full_name}
                    onChange={updateField('full_name')}
                  />
                  <div className="invalid-feedback">Full name is required.</div>
                </div>
                {mode === 'create' && (
                  <div>
                    <label htmlFor="user-password" className="form-label">
                      Password
                    </label>
                    <input
                      id="user-password"
                      type="password"
                      className="form-control"
                      required
                      value={form.password ?? ''}
                      onChange={updateField('password')}
                    />
                    <div className="invalid-feedback">Password is required.</div>
                  </div>
                )}
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
