import { useCallback, useEffect, useState } from 'react'
import type { Role } from '../types/role'
import { roleService } from '../services/roleService'

export function useRole(roleId: string | undefined) {
  const [role, setRole] = useState<Role | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!roleId) {
      return
    }
    setIsLoading(true)
    setError(null)
    try {
      setRole(await roleService.getById(roleId))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load role')
    } finally {
      setIsLoading(false)
    }
  }, [roleId])

  useEffect(() => {
    void load()
  }, [load])

  return { role, isLoading, error, reload: load }
}
