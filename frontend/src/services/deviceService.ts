import { api } from './apiClient'

/** A store assigned to a registered device. */
export interface DeviceStore {
  store_id: string
  store_code: string | null
  store_name: string | null
  is_active: boolean | null
}

/** A machine registered via the zero-config store-agent setup (device identity
 *  = Ed25519 public key + fingerprint). Stores are assigned to it from here. */
export interface Device {
  device_id: string
  device_fingerprint: string
  machine_name: string | null
  app_type: string | null
  app_version: string | null
  status: string
  tenant_id: string | null
  registered_by_username: string | null
  last_seen_at: string | null
  created_at: string | null
  stores: DeviceStore[]
}

interface DevicesResponse {
  devices: Device[]
}

/** A one-time NMV-style device enrollment code, returned exactly once by the
 *  super-admin generate endpoint. Only its hash is ever stored server-side. */
export interface EnrollmentCode {
  store_code: string
  store_id: string
  code_id: string
  enrollment_code: string
  expires_at: string | null
  expires_in_seconds: number
}

export const deviceService = {
  list: () => api.get<DevicesResponse>('/api/devices').then((r) => r.devices),
  /** Mint a one-time enrollment code bound to `storeCode`. The plaintext code is
   *  returned once here and never retrievable again. `ttlSeconds` is optional
   *  (server default ~15 min). Super-admin only. */
  generateEnrollmentCode: (storeCode: string, ttlSeconds?: number) =>
    api.post<EnrollmentCode>(
      `/api/nmv-integration/v1/admin/stores/${encodeURIComponent(storeCode)}/enrollment`,
      ttlSeconds ? { ttl_seconds: ttlSeconds } : {},
    ),
  assignStore: (deviceId: string, storeId: string) =>
    api.post<{ device_id: string; stores: string[] }>(
      `/api/devices/${deviceId}/stores`,
      { store_id: storeId },
    ),
  unassignStore: (deviceId: string, storeId: string) =>
    api.delete<{ device_id: string; stores: string[] }>(
      `/api/devices/${deviceId}/stores/${storeId}`,
    ),
  revoke: (deviceId: string) =>
    api.post<{ device_id: string; status: string }>(`/api/devices/${deviceId}/revoke`, {}),
}
