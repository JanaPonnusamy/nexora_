export interface Tenant {
  tenant_id: string
  tenant_code: string
  tenant_abbreviation: string
  tenant_name: string
  db_name: string
  is_active: boolean
}

export interface TenantInput {
  tenant_code: string
  tenant_abbreviation: string
  tenant_name: string
  db_name: string
}
