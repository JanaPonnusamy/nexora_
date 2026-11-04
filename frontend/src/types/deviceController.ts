export type DcAppKey = 'store_agent' | 'mail_transfer' | 'stock_client' | 'ho_backend' | 'controller'

export interface DcAppStatus {
  app_key: DcAppKey
  installed: boolean
  status: string | null
  version: string | null
  desired_state: string | null
  details: Record<string, unknown> & {
    ho_urls?: string[]
    ho_override?: string | null
    install_dir?: string
    store_id?: string | null
    maintenance?: boolean
    healthy?: boolean
    user_session?: string | null
    legacy_watchdogs?: Record<string, string>
  }
}

export interface DcDesired {
  desired_state: string
  paused_until: string | null
}

export interface DcDevice {
  device_id: string
  machine_name: string | null
  hostname: string | null
  registration_status: string
  registered_by_username: string | null
  registered_at: string | null
  local_ip: string | null
  observed_ip: string | null
  os_version: string | null
  controller_version: string | null
  ho_url: string | null
  last_heartbeat_at: string | null
  online: boolean
  pending_commands: number
  apps: DcAppStatus[]
  stores: { store_id: string; store_code: string; store_name: string }[]
  desired: Partial<Record<DcAppKey, DcDesired>>
}

export interface DcCommand {
  command_id: string
  device_id: string
  app_key: DcAppKey
  action: string
  args: Record<string, unknown>
  status: 'QUEUED' | 'DELIVERED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'CANCELLED' | 'EXPIRED'
  requested_by: string | null
  requested_at: string
  expires_at: string
  delivered_at: string | null
  started_at: string | null
  finished_at: string | null
  exit_code: number | null
  result_text: string | null
}

export interface DcDeviceDetail extends DcDevice {
  commands: DcCommand[]
}

export interface DcPackage {
  app_key: DcAppKey
  version: string
  file_name: string
  sha256: string
  file_size: number
  signature: string | null
  source_urls: string[]
  registered_at: string
}

export interface DcMeta {
  apps: Record<DcAppKey, { label: string; actions: string[] }>
  default_pause_minutes: number
}

export interface DcEnrollCode {
  code: string
  note: string | null
  created_by: string | null
  created_at: string
  expires_at: string
  max_uses: number
  use_count: number
  revoked: boolean
  usable: number
}

export interface DcTerminalSession {
  session_id: string
  device_id: string
  hostname: string | null
  status: 'OPENING' | 'OPEN' | 'CLOSING' | 'CLOSED' | 'FAILED'
  opened_by: string | null
  opened_at: string
  closed_at: string | null
  close_reason: string | null
}

export interface DcTerminalRow {
  seq: number
  direction: 'IN' | 'OUT' | 'SYS'
  data: string
  actor: string | null
  created_at: string
}
