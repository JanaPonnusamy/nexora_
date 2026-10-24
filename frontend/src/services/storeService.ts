import { api } from './apiClient'
import type {
  Store,
  StoreInput,
  StoreCredentials,
  StoreCredentialInput,
  TenantStore,
} from '../types/store'

export const storeService = {
  list: () => api.get<Store[]>('/api/stores'),
  // Selector lists (dropdowns/filters) show active stores only; admin screens
  // that manage stores use list()/getByTenant() to see inactive ones too.
  listActive: () =>
    api.get<Store[]>('/api/stores').then((all) => all.filter((s) => s.is_active)),
  getById: (storeId: string) => api.get<Store>(`/api/stores/${storeId}`),
  getByTenant: (tenantId: string) =>
    api.get<TenantStore[]>(`/api/stores/tenant/${tenantId}`),
  getActiveByTenant: (tenantId: string) =>
    api.get<TenantStore[]>(`/api/stores/tenant/${tenantId}`).then((all) =>
      all.filter((s) => s.is_active !== false),
    ),
  create: (input: StoreInput) => api.post<Store>('/api/stores', input),
  update: (storeId: string, input: StoreInput) =>
    api.put<Store>(`/api/stores/${storeId}`, input),
  setStatus: (storeId: string, isActive: boolean) =>
    api.patch<Store>(`/api/stores/${storeId}/status`, { is_active: isActive }),
  // DB connection credentials (super-admin). Replaces the old manual UPDATE
  // dbo.stores step; the password is encrypted server-side.
  getCredentials: (storeId: string) =>
    api.get<StoreCredentials>(`/api/stores/${storeId}/credentials`),
  updateCredentials: (storeId: string, input: StoreCredentialInput) =>
    api.put<StoreCredentials>(`/api/stores/${storeId}/credentials`, input),
}
