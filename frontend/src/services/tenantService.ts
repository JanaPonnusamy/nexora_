import { api } from './apiClient'
import type { Tenant, TenantInput } from '../types/tenant'

export const tenantService = {
  list: () => api.get<Tenant[]>('/api/tenants'),
  getById: (tenantId: string) => api.get<Tenant>(`/api/tenants/${tenantId}`),
  create: (input: TenantInput) => api.post<Tenant>('/api/tenants', input),
  update: (tenantId: string, input: TenantInput) =>
    api.put<Tenant>(`/api/tenants/${tenantId}`, input),
  setStatus: (tenantId: string, isActive: boolean) =>
    api.patch<Tenant>(`/api/tenants/${tenantId}/status`, { is_active: isActive }),
}
