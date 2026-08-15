export type ActorRole = 'admin' | 'customer' | 'system'
export type AuditStatus = 'success' | 'failure'

export interface AuditLogEntry {
  log_id: string
  actor_id: string | null
  actor_role: ActorRole
  actor_email: string | null
  actor_name: string | null
  action: string
  category: string
  target_type: string | null
  target_id: string | null
  target_label: string | null
  reason: string | null
  metadata: string | null
  ip: string | null
  user_agent: string | null
  device: string | null
  country: string | null
  status: AuditStatus
  error_message: string | null
  timestamp: string
}

export interface AuditFilterParams {
  search?: string
  action?: string
  category?: string
  actor_id?: string
  actor_role?: string
  target_type?: string
  target_id?: string
  status?: string
  from_date?: string
  to_date?: string
  page?: number
  page_size?: number
}

export interface AuditActorOption {
  actor_id: string
  actor_name: string | null
  actor_email: string | null
  actor_role: string | null
}

export interface AuditFilterOptions {
  actors: AuditActorOption[]
  actions: string[]
  categories: string[]
  target_types: string[]
  statuses: string[]
  actor_roles: string[]
}

export interface AuditListResponse {
  items: AuditLogEntry[]
  total: number
  page: number
  page_size: number
  total_pages: number
}
