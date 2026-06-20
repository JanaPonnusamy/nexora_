export interface Module {
  module_id: string
  module_code: string
  module_name: string
  description: string | null
  is_active: boolean
}

export interface ModuleInput {
  module_code: string
  module_name: string
  description: string
}
