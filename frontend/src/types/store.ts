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

/** DB connection details for a store (GET /api/stores/{id}/credentials). The
 *  password is never returned — only whether one is set. */
export interface StoreCredentials {
  store_id: string
  store_code: string
  store_name: string
  server_name: string | null
  database_name: string | null
  username: string | null
  connection_type: string | null
  has_password: boolean
}

/** PUT /api/stores/{id}/credentials. Omit/blank `password` to keep the stored
 *  one while editing the other fields. */
export interface StoreCredentialInput {
  server_name?: string | null
  database_name?: string | null
  username?: string | null
  password?: string | null
  connection_type?: string | null
}
