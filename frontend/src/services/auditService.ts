import { api } from './apiClient'
import type { AuditFilterOptions, AuditFilterParams, AuditListResponse } from '../types/audit'

function buildQuery(params: Record<string, string | number | undefined>): string {
  const qs = Object.entries(params)
    .filter(([, v]) => v != null && v !== '')
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
    .join('&')
  return qs ? `?${qs}` : ''
}

export const auditService = {
  list: (params: AuditFilterParams = {}, signal?: AbortSignal) =>
    api.get<AuditListResponse>(`/api/audit-logs${buildQuery(params as Record<string, string | number | undefined>)}`, signal),

  filterOptions: () =>
    api.get<AuditFilterOptions>('/api/audit-logs/filters'),

  exportCsv: async (params: AuditFilterParams = {}): Promise<Blob> =>
    api.blob(`/api/audit-logs/export${buildQuery(params as Record<string, string | number | undefined>)}`),
}
