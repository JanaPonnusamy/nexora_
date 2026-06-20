export interface Role {
  role_id: string
  role_name: string
  description: string | null
  is_active: boolean
  assigned_users: number | null
  created_at?: string | null
}

export interface RoleInput {
  role_name: string
  description: string
}
