import { useState } from 'react'
import type { FormEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { api, ApiError } from '../services/apiClient'
import logoLockup from '../assets/axythic-logo-white.svg'
import logoMark from '../assets/axythic-mark.svg'
import { APP_NAME } from '../utils/appInfo'
import { ThemeToggle } from '../components/common/ThemeToggle'
import './login.css'

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
  const [showPassword, setShowPassword] = useState(false)

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
    <main className="login-page">
      <div className="login-theme-toggle">
        <ThemeToggle />
      </div>
      <section className="login-showcase" aria-label={`${APP_NAME} platform introduction`}>
        <div className="login-showcase__orb login-showcase__orb--one" aria-hidden="true" />
        <div className="login-showcase__orb login-showcase__orb--two" aria-hidden="true" />
        <div className="login-showcase__content">
          <img className="login-showcase__logo" src={logoLockup} alt={APP_NAME} />
          <div className="login-showcase__copy">
            <span className="login-showcase__eyebrow">Unified operations platform</span>
            <h1>One workspace.<br />Every operation.</h1>
            <p>Run procurement, inventory, reporting and store operations with clarity across your entire network.</p>
          </div>
          <div className="login-showcase__features" aria-label="Platform benefits">
            <span><i className="bi bi-shield-check" aria-hidden="true" /> Secure access</span>
            <span><i className="bi bi-lightning-charge" aria-hidden="true" /> Live workflows</span>
            <span><i className="bi bi-diagram-3" aria-hidden="true" /> Connected stores</span>
          </div>
        </div>
      </section>

      <section className="login-access">
        <div className="login-card">
          <div className="login-card__mobile-brand">
            <img src={logoMark} alt="" aria-hidden="true" />
            <span>{APP_NAME}</span>
          </div>
          <div className="login-card__head">
            <span className="login-card__kicker">Welcome back</span>
            <h2>Sign in to your workspace</h2>
            <p>Enter your account details to continue.</p>
          </div>

          <form className="login-form" onSubmit={handleSubmit}>
            <label className="login-field" htmlFor="login-username">
              <span>Username</span>
              <span className="login-field__control">
                <i className="bi bi-person" aria-hidden="true" />
              <input
                id="login-username"
                autoFocus
                autoComplete="username"
                spellCheck={false}
                placeholder="Enter your username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                disabled={submitting}
              />
              </span>
            </label>

            <label className="login-field" htmlFor="login-password">
              <span>Password</span>
              <span className="login-field__control">
                <i className="bi bi-lock" aria-hidden="true" />
              <input
                id="login-password"
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                placeholder="Enter your password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={submitting}
              />
                <button
                  type="button"
                  className="login-field__reveal"
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  aria-pressed={showPassword}
                  onClick={() => setShowPassword((visible) => !visible)}
                  disabled={submitting}
                >
                  <i className={`bi ${showPassword ? 'bi-eye-slash' : 'bi-eye'}`} aria-hidden="true" />
                </button>
              </span>
            </label>

            {error && (
              <div className="login-error" role="alert">
                <i className="bi bi-exclamation-circle" aria-hidden="true" />
                <span>{error}</span>
              </div>
            )}

            <button type="submit" className="login-submit" disabled={submitting || !username.trim() || !password}>
              {submitting ? (
                <><span className="spinner-border spinner-border-sm" aria-hidden="true" /> Signing in…</>
              ) : (
                <>Sign in <i className="bi bi-arrow-right" aria-hidden="true" /></>
              )}
            </button>
          </form>

          <p className="login-card__foot">
            <i className="bi bi-lock-fill" aria-hidden="true" /> Your session is encrypted and securely managed.
          </p>
        </div>
      </section>
    </main>
  )
}
