import { useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { Header } from '../components/header/Header'
import { Sidebar } from '../components/sidebar/Sidebar'
import { StatusBar } from '../components/statusbar/StatusBar'

/**
 * The application frame: header, navigation, canvas, status bar.
 *
 * The sidebar has a single width — there is no collapsed variant and no
 * toggle. Groups show as one row each and their children open in a flyout,
 * so the nav always fits the viewport without needing to be shrunk.
 */
export function AppShell() {
  const [drawerOpen, setDrawerOpen] = useState(false)
  const { pathname } = useLocation()

  // Navigating closes the mobile drawer. Adjusted during render rather than in
  // an effect so the new page never paints with the drawer still over it.
  const [lastPath, setLastPath] = useState(pathname)
  if (lastPath !== pathname) {
    setLastPath(pathname)
    if (drawerOpen) setDrawerOpen(false)
  }

  return (
    <div className="app-shell">
      <Header onToggleNav={() => setDrawerOpen((open) => !open)} />

      <div className="app-body">
        <Sidebar isMobileOpen={drawerOpen} onNavigate={() => setDrawerOpen(false)} />

        {drawerOpen && (
          <button
            type="button"
            className="app-drawer-scrim d-md-none"
            aria-label="Close navigation"
            onClick={() => setDrawerOpen(false)}
          />
        )}

        <main className="app-main" id="main-content">
          <Outlet />
        </main>
      </div>

      <StatusBar />
    </div>
  )
}
