import { useTheme } from '../../hooks/useTheme'
import { useAuth } from '../../hooks/useAuth'
import { useAccess } from '../../hooks/useAccess'
import { APP_VERSION } from '../../utils/appInfo'

const THEME_LABEL = {
  light: 'Light',
  dark: 'Dark',
  system: 'System',
} as const

export function StatusBar() {
  const { preference } = useTheme()
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
        <i className="bi bi-circle-half" aria-hidden="true" />
        {THEME_LABEL[preference]}
      </span>
      <span className="app-statusbar__item">
        <i className="bi bi-box-seam" aria-hidden="true" />
        Build {APP_VERSION}
      </span>
    </footer>
  )
}
