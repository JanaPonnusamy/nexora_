import { useEffect, useMemo, useState } from 'react'
import type { KpiMetric } from '../types/platform'
import { KPI_DEFINITIONS } from '../components/platform-overview/overviewConfig'

interface PlatformOverviewState {
  metrics: KpiMetric[]
  isLoading: boolean
}

/**
 * Source of truth for the Platform Overview metrics.
 *
 * UI-02 has no backend, so the metrics resolve immediately with unavailable
 * values (rendered as "—"). When the platform statistics endpoint is added,
 * replace the effect body with the fetch and keep `isLoading` driving the
 * skeleton state.
 */
export function usePlatformOverview(): PlatformOverviewState {
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    setIsLoading(false)
  }, [])

  const metrics = useMemo<KpiMetric[]>(
    () => KPI_DEFINITIONS.map((definition) => ({ ...definition, value: null })),
    [],
  )

  return { metrics, isLoading }
}
