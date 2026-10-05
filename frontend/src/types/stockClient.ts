// Shapes returned by /api/stock-client-ops (see backend/modules/stock_client_ops).
// Responses are plain dicts from the repository; these mirror those columns.

export interface StockClientInstallation {
  store_id: string
  store_code: string | null
  store_name: string | null
  tenant_id: string | null
  installation_id: string | null
  client_version: string | null
  watchdog_version: string | null
  client_status: string | null
  watchdog_status: string | null
  last_update_status: string | null
  local_ip: string | null
  observed_ip: string | null
  os_version: string | null
  last_heartbeat_at: string | null
  last_error: string | null
  installation_status: string | null
  target_version: string | null
  // derived server-side (service._decorate_connectivity)
  connectivity: 'ONLINE' | 'STALE' | 'OFFLINE'
  watchdog: 'ONLINE' | 'OFFLINE'
  client: string
  version_status: 'UP TO DATE' | 'UPDATE AVAILABLE' | 'OFFLINE'
}

export interface StockClientEvent {
  event_type: string
  actor: string | null
  detail: string | null
  target_version: string | null
  result: string | null
  created_at: string | null
}

export interface StockClientInstallationDetail extends Omit<StockClientInstallation,
  'connectivity' | 'watchdog' | 'client' | 'version_status'> {
  device_id: string | null
  fingerprint_hash: string | null
  hostname: string | null
  registered_at: string | null
  status: string | null
  connectivity?: StockClientInstallation['connectivity']
  watchdog?: StockClientInstallation['watchdog']
  client?: string
  version_status?: StockClientInstallation['version_status']
  events: StockClientEvent[]
}

export interface StockClientRelease {
  id: string
  version: string
  release_id: string
  build: string | null
  file_name: string
  sha256: string
  file_size: number
  status: 'DRAFT' | 'TESTING' | 'APPROVED' | 'ROLLED_OUT' | 'RETIRED'
  release_notes: string | null
  min_supported_version: string | null
  created_by: string | null
  created_at: string | null
  approved_by: string | null
  approved_at: string | null
}

export interface StockClientDeploymentTarget {
  id: string
  store_id: string
  store_code: string | null
  store_name: string | null
  installation_id: string | null
  current_version: string | null
  target_version: string
  status: string
  progress: number
  error: string | null
  started_at: string | null
  completed_at: string | null
  updated_at: string | null
}

export interface StockClientDeployment {
  id: string
  rollout_id: string
  release_version: string | null
  scope: 'ALL' | 'SELECTED'
  status: 'DRAFT' | 'PENDING' | 'IN_PROGRESS' | 'COMPLETED' | 'CANCELLED'
  created_by: string | null
  created_at: string | null
  authorized_by: string | null
  authorized_at: string | null
  completed_at: string | null
  target_count: number
  success_count: number
  failed_count: number
}

export interface StockClientDeploymentDetail extends Omit<StockClientDeployment,
  'target_count' | 'success_count' | 'failed_count'> {
  release_id: string
  targets: StockClientDeploymentTarget[]
}

export interface DeploymentCreateBody {
  release_id: string
  scope: 'ALL' | 'SELECTED'
  store_ids: string[]
}
