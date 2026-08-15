import { useTheme } from '../../hooks/useTheme'
import { useAuth } from '../../hooks/useAuth'
import { useAccess } from '../../hooks/useAccess'
import { APP_VERSION } from '../../utils/appInfo'

export function StatusBar() {
  const { theme } = useTheme()
  const { user } = useAuth()
  const { currentRole } = useAccess()

  return (
    <footer className="app-statusbar">
      <span className="app-statusbar__item app-statusbar__item--live">
        <i className="bi bi-circle-fill" aria-hidden="true" />
        Connected
      </span>

      {user?.tenant && (
        <span className="app-statusbar__item">
          <i className="bi bi-building" aria-hidden="true" />
          {user.tenant}
        </span>
      )}

      {currentRole?.role_name && (
        <span className="app-statusbar__item">
          <i className="bi bi-person-badge" aria-hidden="true" />
          {currentRole.role_name}
        </span>
      )}

      <span className="app-statusbar__spacer" />

      <span className="app-statusbar__item">
        <i className={`bi ${theme === 'dark' ? 'bi-moon-stars' : 'bi-sun'}`} aria-hidden="true" />
        {theme === 'dark' ? 'Dark' : 'Light'}
      </span>
      <span className="app-statusbar__item">
        <i className="bi bi-box-seam" aria-hidden="true" />
        Build {APP_VERSION}
      </span>
    </footer>
  )
}
