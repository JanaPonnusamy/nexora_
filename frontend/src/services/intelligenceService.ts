import { api } from './apiClient'
import type {
  PiBuildResult,
  PiDetail,
  PiGrid,
  PiHover,
  PiSummary,
} from '../types/intelligence'

function qs(params: Record<string, string | number | undefined>): string {
  const parts = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== '' && v !== null)
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
  return parts.length ? `?${parts.join('&')}` : ''
}

/** Product Intelligence Workspace API. The grid/detail/summary read the backend
 *  cache only; hover is the sole on-demand history read (lazy, per store cell). */
export const intelligenceService = {
  build: (tenantId: string, refreshId?: string, by?: string | null) =>
    api.post<PiBuildResult>(`/api/procurement/intelligence/build`, {
      tenant_id: tenantId,
      refresh_id: refreshId,
      created_by: by ?? undefined,
    }),

  grid: (tenantId: string, refreshId?: string, search?: string) =>
    api.get<PiGrid>(
      `/api/procurement/intelligence${qs({ tenant_id: tenantId, refresh_id: refreshId, search })}`,
    ),

  summary: (tenantId: string, refreshId?: string) =>
    api.get<PiSummary & { build_id: string; generated_on: string }>(
      `/api/procurement/intelligence/summary${qs({ tenant_id: tenantId, refresh_id: refreshId })}`,
    ),

  detail: (cacheId: string) =>
    api.get<PiDetail>(`/api/procurement/intelligence/${cacheId}`),

  hover: (cacheId: string, storeId: string) =>
    api.get<PiHover>(`/api/procurement/intelligence/${cacheId}/hover/${storeId}`),
}
