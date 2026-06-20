import { useTheme } from '../../hooks/useTheme'
import { useAuth } from '../../hooks/useAuth'
import { APP_VERSION } from '../../utils/appInfo'

export function StatusBar() {
  const { theme } = useTheme()
  const { user } = useAuth()

  return (
    <footer className="app-statusbar">
      <div className="app-statusbar__group">
        <span className="app-statusbar__item app-statusbar__item--accent">
          <i className="bi bi-circle-fill" aria-hidden="true" />
          {theme === 'dark' ? 'Dark' : 'Light'} theme
        </span>
        <span className="app-statusbar__item">
          <i className="bi bi-box-seam" aria-hidden="true" />
          Build {APP_VERSION}
        </span>
      </div>

      <div className="app-statusbar__group ms-auto">
        <span className="app-statusbar__item d-none d-md-inline-flex">
          <i className="bi bi-person" aria-hidden="true" />
          {user?.fullName ?? '—'}
        </span>
        <span className="app-statusbar__item d-none d-md-inline-flex">
          <i className="bi bi-building" aria-hidden="true" />
          {user?.tenant ?? '—'}
        </span>
      </div>
    </footer>
  )
}
