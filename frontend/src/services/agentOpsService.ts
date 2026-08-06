import { api } from './apiClient'
import type { AgentOpsLogRow, AgentOpsRow, AgentRelease } from '../types/sync'

export const agentOpsService = {
  list: (tenantId?: string) =>
    api.get<AgentOpsRow[]>(`/api/agent-ops/stores${tenantId ? `?tenant_id=${encodeURIComponent(tenantId)}` : ''}`),
  releases: () => api.get<AgentRelease[]>('/api/agent-ops/releases'),
  logs: (storeId?: string) =>
    api.get<AgentOpsLogRow[]>(`/api/agent-ops/logs?limit=40${storeId ? `&store_id=${encodeURIComponent(storeId)}` : ''}`),
  setState: (storeId: string, desiredState: 'RUNNING' | 'STOPPED') =>
    api.post<{ store_id: string; desired_state: string }>(
      `/api/agent-ops/stores/${storeId}/state`,
      { desired_state: desiredState },
    ),
  setStateBulk: (storeIds: string[], desiredState: 'RUNNING' | 'STOPPED') =>
    api.post<{ updated: number; desired_state: string }>('/api/agent-ops/stores/state-bulk', {
      store_ids: storeIds,
      desired_state: desiredState,
    }),
  setVersion: (storeId: string, desiredVersion: string | null) =>
    api.post<{ store_id: string; desired_version: string | null }>(
      `/api/agent-ops/stores/${storeId}/version`,
      { desired_version: desiredVersion },
    ),
  setVersionBulk: (storeIds: string[], desiredVersion: string | null) =>
    api.post<{ updated: number; desired_version: string | null }>('/api/agent-ops/stores/version-bulk', {
      store_ids: storeIds,
      desired_version: desiredVersion,
    }),
}
