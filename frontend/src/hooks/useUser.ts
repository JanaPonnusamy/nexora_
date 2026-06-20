import { useCallback, useEffect, useState } from 'react'
import type { User } from '../types/user'
import { userService } from '../services/userService'

export function useUser(userId: string | undefined) {
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!userId) {
      return
    }
    setIsLoading(true)
    setError(null)
    try {
      setUser(await userService.getById(userId))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load user')
    } finally {
      setIsLoading(false)
    }
  }, [userId])

  useEffect(() => {
    void load()
  }, [load])

  return { user, isLoading, error, reload: load }
}
