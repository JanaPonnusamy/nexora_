import { useCallback, useEffect, useState } from 'react'
import type { UserRoleAssignment } from '../types/userRole'
import { userRoleService } from '../services/userRoleService'

export function useUserRoles(userId: string | undefined) {
  const [assignments, setAssignments] = useState<UserRoleAssignment[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!userId) {
      return
    }
    setIsLoading(true)
    setError(null)
    try {
      setAssignments(await userRoleService.getByUser(userId))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load assignments')
    } finally {
      setIsLoading(false)
    }
  }, [userId])

  useEffect(() => {
    void load()
  }, [load])

  return { assignments, isLoading, error, reload: load }
}
