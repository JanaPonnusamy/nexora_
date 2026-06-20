export interface Store {
  store_id: string
  tenant_id: string
  store_code: string
  store_name: string
  server_name: string
  database_name: string
  is_active: boolean
}

export interface StoreInput {
  tenant_id: string
  store_code: string
  store_name: string
  server_name: string
  database_name: string
}

/** Lightweight shape returned by GET /api/stores/tenant/{id}. */
export interface TenantStore {
  store_id: string
  store_code: string
  store_name: string
}
