import { api } from './apiClient'
import type { PermissionMatrix } from '../types/permission'

export const permissionService = {
  getMatrix: () => api.get<PermissionMatrix>('/api/permissions/matrix'),
  assign: (roleId: string, moduleId: string) =>
    api.post('/api/permissions/assign', { role_id: roleId, module_id: moduleId }),
  remove: (roleId: string, moduleId: string) =>
    api.delete('/api/permissions/assign', { role_id: roleId, module_id: moduleId }),
}
