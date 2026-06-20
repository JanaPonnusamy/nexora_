import { api } from './apiClient'
import type { User, UserInput, UserListParams } from '../types/user'

function buildQuery(params: UserListParams): string {
  const query = new URLSearchParams()
  if (params.tenantId) query.set('tenant_id', params.tenantId)
  if (params.storeId) query.set('store_id', params.storeId)
  if (params.roleId) query.set('role_id', params.roleId)
  if (params.status) query.set('status', params.status)
  const serialized = query.toString()
  return serialized ? `?${serialized}` : ''
}

export const userService = {
  list: (params: UserListParams = {}) => api.get<User[]>(`/api/users${buildQuery(params)}`),
  getById: (userId: string) => api.get<User>(`/api/users/${userId}`),
  create: (input: UserInput) => api.post<User>('/api/users', input),
  update: (userId: string, input: UserInput) => api.put<User>(`/api/users/${userId}`, input),
  setStatus: (userId: string, isActive: boolean) =>
    api.patch<User>(`/api/users/${userId}/status`, { is_active: isActive }),
}
