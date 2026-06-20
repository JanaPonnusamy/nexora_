export interface User {
  user_id: string
  username: string
  full_name: string
  is_active: boolean
  last_login: string | null
  store_count: number | null
  role_count: number | null
}

export interface UserInput {
  username: string
  full_name: string
  password?: string
}

export interface UserListParams {
  tenantId?: string
  storeId?: string
  roleId?: string
  status?: 'active' | 'inactive'
}
