import { useCallback, useEffect, useState } from 'react'
import type { TenantStore } from '../types/store'
import { storeService } from '../services/storeService'

export function useTenantStores(tenantId: string | undefined) {
  const [stores, setStores] = useState<TenantStore[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!tenantId) {
      return
    }
    setIsLoading(true)
    setError(null)
    try {
      setStores(await storeService.getByTenant(tenantId))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load stores')
    } finally {
      setIsLoading(false)
    }
  }, [tenantId])

  useEffect(() => {
    void load()
  }, [load])

  return { stores, isLoading, error, reload: load }
}
