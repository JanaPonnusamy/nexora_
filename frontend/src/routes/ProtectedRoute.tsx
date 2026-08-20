import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'

interface ProtectedRouteProps {
  children: ReactNode
}

/** Redirects to /login when there's no valid session. While a stored token is
 *  being restored (page reload) renders nothing rather than bouncing to
 *  /login and back. */
export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const { isAuthenticated, restoring } = useAuth()
  const location = useLocation()

  if (restoring) {
    return null
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />
  }

  return <>{children}</>
}
