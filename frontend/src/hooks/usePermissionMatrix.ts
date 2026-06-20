import { useCallback, useEffect, useState } from 'react'
import type { PermissionMatrix } from '../types/permission'
import { permissionService } from '../services/permissionService'

export function usePermissionMatrix() {
  const [matrix, setMatrix] = useState<PermissionMatrix | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      setMatrix(await permissionService.getMatrix())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load permission matrix')
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  return { matrix, isLoading, error, reload: load }
}
