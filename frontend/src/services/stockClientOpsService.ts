import { api } from './apiClient'
import type {
  DeploymentCreateBody,
  StockClientDeployment,
  StockClientDeploymentDetail,
  StockClientInstallation,
  StockClientInstallationDetail,
  StockClientRelease,
} from '../types/stockClient'

// HO admin surface for Stock Client fleet management (super-admin only server
// side). Mirrors services/agentOpsService.ts.
export const stockClientOpsService = {
  installations: () =>
    api.get<{ installations: StockClientInstallation[] }>('/api/stock-client-ops/installations'),
  installation: (id: string) =>
    api.get<StockClientInstallationDetail>(`/api/stock-client-ops/installations/${id}`),

  releases: () => api.get<{ releases: StockClientRelease[] }>('/api/stock-client-ops/releases'),
  approveRelease: (id: string) =>
    api.post<StockClientRelease>(`/api/stock-client-ops/releases/${id}/approve`, {}),
  retireRelease: (id: string) =>
    api.post<StockClientRelease>(`/api/stock-client-ops/releases/${id}/retire`, {}),

  deployments: () => api.get<{ deployments: StockClientDeployment[] }>('/api/stock-client-ops/deployments'),
  deployment: (id: string) =>
    api.get<StockClientDeploymentDetail>(`/api/stock-client-ops/deployments/${id}`),
  createDeployment: (body: DeploymentCreateBody) =>
    api.post<StockClientDeploymentDetail>('/api/stock-client-ops/deployments', body),
  authorizeDeployment: (id: string) =>
    api.post<StockClientDeploymentDetail>(`/api/stock-client-ops/deployments/${id}/authorize`, {}),
  cancelDeployment: (id: string) =>
    api.post<StockClientDeploymentDetail>(`/api/stock-client-ops/deployments/${id}/cancel`, {}),
  retryTarget: (deploymentId: string, targetId: string) =>
    api.post<StockClientDeploymentDetail>(
      `/api/stock-client-ops/deployments/${deploymentId}/targets/${targetId}/retry`,
      {},
    ),
}
