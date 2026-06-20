import { useCallback, useEffect, useState } from 'react'
import type { Store } from '../types/store'
import { storeService } from '../services/storeService'

export function useStore(storeId: string | undefined) {
  const [store, setStore] = useState<Store | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!storeId) {
      return
    }
    setIsLoading(true)
    setError(null)
    try {
      setStore(await storeService.getById(storeId))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load store')
    } finally {
      setIsLoading(false)
    }
  }, [storeId])

  useEffect(() => {
    void load()
  }, [load])

  return { store, isLoading, error, reload: load }
}
