import { useEffect, useRef, useState } from 'react'
import { Outlet } from 'react-router-dom'
import { Header } from '../components/header/Header'
import { Sidebar } from '../components/sidebar/Sidebar'
import { StatusBar } from '../components/statusbar/StatusBar'
import { settingsService } from '../platform/services/SettingsService'
import { useMediaQuery } from '../hooks/useMediaQuery'

// Same threshold the Purchase Workspace uses for its own responsive split
// (useNarrowWorkspace) — one consistent "low viewport monitor" definition
// across the app, covering 1280x720 / 1366x768.
const NARROW_VIEWPORT_QUERY = '(max-width: 1366px)'

export function AppShell() {
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const isNarrowViewport = useMediaQuery(NARROW_VIEWPORT_QUERY)

  // Icon-only sidebar (spec: side menu "take more space" on low-viewport
  // monitors — 720p/768p in particular). Before the user has ever touched
  // the toggle, default to collapsed on a narrow viewport and expanded on a
  // normal one, and keep following live resizes; the moment they explicitly
  // toggle it, that choice is remembered and wins from then on, same
  // "narrow-default-until-user-choice" pattern the Purchase Workspace's
  // column config already uses.
  const userSetRef = useRef(settingsService.get<boolean | null>('appShell.sidebarCollapsed', null) !== null)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() =>
    settingsService.get<boolean | null>('appShell.sidebarCollapsed', null) ?? isNarrowViewport,
  )

  useEffect(() => {
    if (userSetRef.current) return
    setSidebarCollapsed(isNarrowViewport)
  }, [isNarrowViewport])

  const toggleSidebar = () => {
    userSetRef.current = true
    setSidebarCollapsed((v) => {
      const next = !v
      settingsService.set('appShell.sidebarCollapsed', next)
      return next
    })
  }

  return (
    <div className="app-shell">
      <Header
        onToggleNav={() => setMobileNavOpen((open) => !open)}
        sidebarCollapsed={sidebarCollapsed}
        onToggleSidebar={toggleSidebar}
      />
      <div className="app-body">
        <Sidebar isMobileOpen={mobileNavOpen} onNavigate={() => setMobileNavOpen(false)} collapsed={sidebarCollapsed} />
        {mobileNavOpen && (
          <div
            className="app-sidebar-backdrop d-md-none"
            onClick={() => setMobileNavOpen(false)}
          />
        )}
        <main className="app-main">
          <Outlet />
        </main>
      </div>
      <StatusBar />
    </div>
  )
}
