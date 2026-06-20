import { useCallback, useEffect, useState } from 'react'
import type { Tenant } from '../types/tenant'
import { tenantService } from '../services/tenantService'

export function useTenant(tenantId: string | undefined) {
  const [tenant, setTenant] = useState<Tenant | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!tenantId) {
      return
    }
    setIsLoading(true)
    setError(null)
    try {
      setTenant(await tenantService.getById(tenantId))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load tenant')
    } finally {
      setIsLoading(false)
    }
  }, [tenantId])

  useEffect(() => {
    void load()
  }, [load])

  return { tenant, isLoading, error, reload: load }
}
