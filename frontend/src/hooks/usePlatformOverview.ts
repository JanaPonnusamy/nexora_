import { useCallback, useEffect, useState } from 'react'
import type { KpiMetric } from '../types/platform'
import { KPI_DEFINITIONS } from '../components/platform-overview/overviewConfig'
import { tenantService } from '../services/tenantService'
import { storeService } from '../services/storeService'
import { userService } from '../services/userService'
import { roleService } from '../services/roleService'
import { moduleService } from '../services/moduleService'

interface PlatformOverviewState {
  metrics: KpiMetric[]
  isLoading: boolean
  error: string | null
  reload: () => Promise<void>
}

/**
 * Real Platform Overview metrics — counts come from the live list endpoints
 * (tenants/stores/users/roles/modules), not placeholder values.
 */
export function usePlatformOverview(): PlatformOverviewState {
  const [metrics, setMetrics] = useState<KpiMetric[]>(
    KPI_DEFINITIONS.map((definition) => ({ ...definition, value: null })),
  )
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const [tenants, stores, users, roles, modules] = await Promise.all([
        tenantService.list(),
        storeService.list(),
        userService.list(),
        roleService.list(),
        moduleService.list(),
      ])
      const counts: Record<string, number> = {
        tenants: tenants.length,
        stores: stores.length,
        users: users.length,
        roles: roles.length,
        modules: modules.length,
      }
      setMetrics(KPI_DEFINITIONS.map((definition) => ({ ...definition, value: counts[definition.key] ?? 0 })))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load metrics')
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  return { metrics, isLoading, error, reload: load }
}
