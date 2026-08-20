import { Suspense } from 'react'
import { RouterProvider } from 'react-router-dom'
import { ThemeProvider } from './contexts/ThemeContext'
import { AuthProvider } from './contexts/AuthContext'
import { RoleProvider } from './contexts/RoleContext'
import { SessionProvider } from './platform/session/SessionContext'
import { appRouter } from './routes/AppRouter'

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <RoleProvider>
          <SessionProvider>
            <Suspense
              fallback={
                <div className="app-route-loading" role="status" aria-live="polite">
                  <span className="spinner-border spinner-border-sm" aria-hidden="true" />
                  Loading workspace…
                </div>
              }
            >
              <RouterProvider router={appRouter} />
            </Suspense>
          </SessionProvider>
        </RoleProvider>
      </AuthProvider>
    </ThemeProvider>
  )
}
