import { useContext } from 'react'
import { RoleContext } from '../contexts/RoleContext'

/** Access to the current active role + navigation capabilities. */
export function useAccess() {
  const context = useContext(RoleContext)
  if (!context) {
    throw new Error('useAccess must be used within a RoleProvider')
  }
  return context
}
