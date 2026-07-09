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
            <RouterProvider router={appRouter} />
          </SessionProvider>
        </RoleProvider>
      </AuthProvider>
    </ThemeProvider>
  )
}
