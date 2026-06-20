export interface PermissionRole {
  role_id: string
  role_name: string
}

export interface PermissionModule {
  module_id: string
  module_code: string
  module_name: string
}

export interface PermissionAssignment {
  role_id: string
  module_id: string
}

export interface PermissionMatrix {
  roles: PermissionRole[]
  modules: PermissionModule[]
  assignments: PermissionAssignment[]
}
