import { useCallback, useEffect, useState } from 'react'
import type { User, UserListParams } from '../types/user'
import { userService } from '../services/userService'

export function useUsers(params: UserListParams) {
  const { tenantId, storeId, roleId, status } = params
  const [users, setUsers] = useState<User[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      setUsers(await userService.list({ tenantId, storeId, roleId, status }))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load users')
    } finally {
      setIsLoading(false)
    }
  }, [tenantId, storeId, roleId, status])

  useEffect(() => {
    void load()
  }, [load])

  return { users, isLoading, error, reload: load }
}
