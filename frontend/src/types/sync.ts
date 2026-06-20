export interface SyncKpis {
  stores_online: number
  stores_offline: number
  sync_running: number
  queued: number
  completed_today: number
  failed_today: number
}

export interface ControlCenterStore {
  store_id: string
  store_code: string
  store_name: string
  connection_type: string
  agent_status: string
  last_sync: string | null
  current_activity: string
  is_syncing: boolean
  status: string
}

export interface ControlCenter {
  kpis: SyncKpis
  stores: ControlCenterStore[]
}

export interface SyncSchedule {
  schedule_id: number
  schedule_name: string
  schedule_type: string | null
  start_time: string | null
  is_enabled: boolean
}

export interface StoreHealthRow {
  store_id: string
  store_code: string
  store_name: string
  connection_type: string
  last_heartbeat: string | null
  agent_status: string
  last_sync: string | null
  pending_queue: number
}

export interface SyncHistoryRow {
  sync_id: number
  store_id: string | null
  store_code: string | null
  store_name: string | null
  scope: string | null
  started_at: string | null
  completed_at: string | null
  duration_seconds: number | null
  rows: number
  status: string | null
}

export interface CatalogTable {
  schema_name: string
  table_name: string
}

export interface SyncTable {
  sync_table_id: string
  table_name: string
  is_active: boolean
  sync_mode: string
  watermark_column: string | null
  window_days: number | null
  custom_where: string | null
  sync_order: number
}

export interface SyncTableInput {
  table_name: string
  sync_mode: string
  watermark_column: string | null
  window_days: number | null
  custom_where: string | null
  sync_order: number
  is_active: boolean
}

export interface TableColumn {
  column_name: string
  data_type: string
  column_order: number
  catalog_is_pk: boolean
  is_selected: boolean
  is_pk: boolean
  is_hash: boolean
  is_watermark: boolean
}

export interface TableColumns {
  table_name: string
  columns: TableColumn[]
}
