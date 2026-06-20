import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import { Header } from '../components/header/Header'
import { Sidebar } from '../components/sidebar/Sidebar'
import { StatusBar } from '../components/statusbar/StatusBar'

export function AppShell() {
  const [mobileNavOpen, setMobileNavOpen] = useState(false)

  return (
    <div className="app-shell">
      <Header onToggleNav={() => setMobileNavOpen((open) => !open)} />
      <div className="app-body">
        <Sidebar isMobileOpen={mobileNavOpen} onNavigate={() => setMobileNavOpen(false)} />
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
