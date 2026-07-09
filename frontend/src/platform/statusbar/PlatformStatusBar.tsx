import type { ReactNode } from 'react'
import { useTheme } from '../../hooks/useTheme'
import { useAuth } from '../../hooks/useAuth'
import { useSession } from '../session/SessionContext'
import { APP_VERSION } from '../../utils/appInfo'

export interface StatusBarItem {
  id: string
  content: ReactNode
  align?: 'start' | 'end'
}

interface PlatformStatusBarProps {
  /** Extra items contributed by the shell/active module (e.g. sync status, API status). */
  items?: StatusBarItem[]
}

/**
 * Generalized, contribution-based evolution of
 * components/statusbar/StatusBar.tsx (left untouched — still used by the
 * live AppShell). Theme/version/user/store are the platform's own default
 * items; callers add more via `items` instead of a module rolling its own
 * status bar.
 */
export function PlatformStatusBar({ items = [] }: PlatformStatusBarProps) {
  const { theme } = useTheme()
  const { user } = useAuth()
  const { storeId } = useSession()

  const defaultItems: StatusBarItem[] = [
    {
      id: 'theme',
      align: 'start',
      content: (
        <>
          <i className="bi bi-circle-fill" aria-hidden="true" />
          {theme === 'dark' ? 'Dark' : 'Light'} theme
        </>
      ),
    },
    {
      id: 'version',
      align: 'start',
      content: (
        <>
          <i className="bi bi-box-seam" aria-hidden="true" />
          Build {APP_VERSION}
        </>
      ),
    },
    {
      id: 'store',
      align: 'end',
      content: (
        <>
          <i className="bi bi-shop" aria-hidden="true" />
          {storeId ?? 'No store selected'}
        </>
      ),
    },
    {
      id: 'user',
      align: 'end',
      content: (
        <>
          <i className="bi bi-person" aria-hidden="true" />
          {user?.fullName ?? '—'}
        </>
      ),
    },
  ]

  const allItems = [...defaultItems, ...items]
  const startItems = allItems.filter((item) => item.align !== 'end')
  const endItems = allItems.filter((item) => item.align === 'end')

  return (
    <footer className="app-statusbar platform-statusbar">
      <div className="app-statusbar__group">
        {startItems.map((item) => (
          <span key={item.id} className="app-statusbar__item">
            {item.content}
          </span>
        ))}
      </div>
      <div className="app-statusbar__group ms-auto">
        {endItems.map((item) => (
          <span key={item.id} className="app-statusbar__item">
            {item.content}
          </span>
        ))}
      </div>
    </footer>
  )
}
