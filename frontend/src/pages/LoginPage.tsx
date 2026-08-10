import { useState } from 'react'
import type { FormEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { api, ApiError } from '../services/apiClient'

interface LoginResponse {
  token: string
  token_type: string
  user: {
    user_id: string
    username: string
    first_name: string
    is_platform_user: boolean
    is_active: boolean
    tenant_id: string | null
    modules: unknown[]
    roles: { role_id: string; role_name: string; store_id: string; store_code: string; store_name: string }[]
  }
}

export default function LoginPage() {
  const { isAuthenticated, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  if (isAuthenticated) {
    const redirectTo = (location.state as { from?: string } | null)?.from || '/'
    return <Navigate to={redirectTo} replace />
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const res = await api.post<LoginResponse>('/api/auth/login', { username, password })
      const primaryRole = res.user.roles?.[0]
      login(res.token, {
        id: res.user.user_id,
        username: res.user.username,
        fullName: res.user.first_name,
        tenant: res.user.tenant_id ?? '',
        isPlatformUser: res.user.is_platform_user,
        roleNames: res.user.roles.map((r) => r.role_name),
        storeId: primaryRole?.store_id ?? '',
        storeCode: primaryRole?.store_code ?? '',
      })
      navigate('/', { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to reach the server.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="d-flex align-items-center justify-content-center vh-100 bg-body-tertiary">
      <div className="card shadow-sm" style={{ width: 360 }}>
        <div className="card-body p-4">
          <h1 className="h4 mb-3 text-center">NEXORA</h1>
          <form onSubmit={handleSubmit}>
            <div className="mb-3">
              <label className="form-label" htmlFor="login-username">Username</label>
              <input
                id="login-username"
                className="form-control"
                autoFocus
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                disabled={submitting}
              />
            </div>
            <div className="mb-3">
              <label className="form-label" htmlFor="login-password">Password</label>
              <input
                id="login-password"
                type="password"
                className="form-control"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={submitting}
              />
            </div>
            {error && <div className="alert alert-danger py-2">{error}</div>}
            <button type="submit" className="btn btn-primary w-100" disabled={submitting || !username || !password}>
              {submitting ? 'Signing in…' : 'Sign In'}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}
