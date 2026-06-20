import { api } from './apiClient'
import type { UserRoleAssignment } from '../types/userRole'

export const userRoleService = {
  getByUser: (userId: string) =>
    api.get<UserRoleAssignment[]>(`/api/user-roles/user/${userId}`),
}
