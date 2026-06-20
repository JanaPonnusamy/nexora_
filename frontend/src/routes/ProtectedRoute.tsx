import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'

interface ProtectedRouteProps {
  children: ReactNode
}

/**
 * Route guard foundation. When auth is wired up, an unauthenticated user will
 * be redirected to the login route. For UI-01B `isAuthenticated` is always
 * true, so this renders its children unchanged.
 */
export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const { isAuthenticated } = useAuth()

  if (!isAuthenticated) {
    return <Navigate to="/overview" replace />
  }

  return <>{children}</>
}
