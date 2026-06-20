import { useCallback, useEffect, useState } from 'react'
import type { Tenant } from '../types/tenant'
import { tenantService } from '../services/tenantService'

export function useTenants() {
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      setTenants(await tenantService.list())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load tenants')
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  return { tenants, isLoading, error, reload: load }
}
