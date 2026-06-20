import { api } from './apiClient'
import type { Store, StoreInput, TenantStore } from '../types/store'

export const storeService = {
  list: () => api.get<Store[]>('/api/stores'),
  getById: (storeId: string) => api.get<Store>(`/api/stores/${storeId}`),
  getByTenant: (tenantId: string) =>
    api.get<TenantStore[]>(`/api/stores/tenant/${tenantId}`),
  create: (input: StoreInput) => api.post<Store>('/api/stores', input),
  update: (storeId: string, input: StoreInput) =>
    api.put<Store>(`/api/stores/${storeId}`, input),
  setStatus: (storeId: string, isActive: boolean) =>
    api.patch<Store>(`/api/stores/${storeId}/status`, { is_active: isActive }),
}
