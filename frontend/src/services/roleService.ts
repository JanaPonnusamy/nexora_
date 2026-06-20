import { api } from './apiClient'
import type { Role, RoleInput } from '../types/role'

export const roleService = {
  list: () => api.get<Role[]>('/api/roles'),
  getById: (roleId: string) => api.get<Role>(`/api/roles/${roleId}`),
  create: (input: RoleInput) => api.post<Role>('/api/roles', input),
  update: (roleId: string, input: RoleInput) => api.put<Role>(`/api/roles/${roleId}`, input),
  setStatus: (roleId: string, isActive: boolean) =>
    api.patch<Role>(`/api/roles/${roleId}/status`, { is_active: isActive }),
}
