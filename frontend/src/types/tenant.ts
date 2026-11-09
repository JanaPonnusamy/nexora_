export interface Tenant {
  tenant_id: string
  tenant_code: string
  tenant_abbreviation: string
  tenant_name: string
  db_name: string
  is_active: boolean
  // Central Legacy Order DB (OrderNMC/OrderSMS/...) this tenant's stores use.
  // Blank keeps the single-tenant default / LEGACY_DB_DATABASE_BY_TENANT.
  legacy_db_name: string | null
}

export interface TenantInput {
  tenant_code: string
  tenant_abbreviation: string
  tenant_name: string
  db_name: string
  legacy_db_name: string
}
