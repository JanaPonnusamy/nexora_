import { api } from './apiClient'
import type { Module, ModuleInput } from '../types/module'

export const moduleService = {
  list: () => api.get<Module[]>('/api/modules'),
  getById: (moduleId: string) => api.get<Module>(`/api/modules/${moduleId}`),
  create: (input: ModuleInput) => api.post<Module>('/api/modules', input),
  update: (moduleId: string, input: ModuleInput) =>
    api.put<Module>(`/api/modules/${moduleId}`, input),
  setStatus: (moduleId: string, isActive: boolean) =>
    api.patch<Module>(`/api/modules/${moduleId}/status`, { is_active: isActive }),
}
