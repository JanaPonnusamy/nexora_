import type { ReactNode } from 'react'
import { Navigate } from 'react-router-dom'
import type { Capability } from '../types/access'
import { useAccess } from '../hooks/useAccess'

/** Route guard — renders children only when the active role has the capability,
 *  otherwise redirects to the role's landing page. */
export function RequireCapability({ cap, children }: { cap: Capability; children: ReactNode }) {
  const { can, landingPath, ready } = useAccess()
  if (!ready) return null
  if (!can(cap)) return <Navigate to={landingPath} replace />
  return <>{children}</>
}
