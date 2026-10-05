import { api } from './apiClient'
import type {
  HoNodeStatus,
  SelfUpdateResult,
  UpdateNodeTarget,
  UpdateNodesResult,
} from '../types/hoOps'

// HO backend self-update surface (super-admin only server side). The node
// serving the UI orchestrates its peers server-side, so the browser only ever
// talks to its own origin.
export const hoOpsService = {
  status: () => api.get<HoNodeStatus>('/api/ho-ops/status'),
  nodes: () => api.get<{ nodes: HoNodeStatus[] }>('/api/ho-ops/nodes'),
  selfUpdate: () => api.post<SelfUpdateResult>('/api/ho-ops/self-update', {}),
  update: (targets: UpdateNodeTarget[]) =>
    api.post<UpdateNodesResult>('/api/ho-ops/update', { targets }),
}
