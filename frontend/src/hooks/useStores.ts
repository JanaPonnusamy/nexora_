import { useCallback, useEffect, useState } from 'react'
import type { Store } from '../types/store'
import { storeService } from '../services/storeService'

export function useStores() {
  const [stores, setStores] = useState<Store[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      setStores(await storeService.list())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load stores')
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  return { stores, isLoading, error, reload: load }
}
