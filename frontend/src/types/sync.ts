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
  tenant_id: string | null
  store_id: string | null
  store_code: string | null
  store_name: string | null
  schedule_name: string
  schedule_type: string | null
  start_time: string | null
  sync_mode: string | null
  is_enabled: boolean
  suspended_until: string | null
  last_run_at: string | null
  created_at: string | null
  status: string
}

export interface ScheduleInput {
  schedule_name: string
  schedule_type: string
  store_id: string | null
  start_time: string
  sync_mode: string
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

/** A discovered catalog table joined to its configured state (if any). */
export interface AvailableTable {
  schema_name: string
  table_name: string
  sync_table_id: string | null
  is_configured: boolean
  is_active: boolean
  sync_mode: string | null
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

export interface SyncTaskResult {
  task_id: string
  status: string
}

export interface PendingTask {
  execution_id: string
  tenant_id: string
  store_id: string
  execution_type: string
  sync_mode: string
  execution_status: string
  started_at: string | null
  total_tables: number
}

export interface LiveStore {
  store_id: string
  store_code: string | null
  store_name: string | null
  execution_id: string
  status: string
  sync_type: string | null
  current_table: string | null
  chunk_no: number | null
  total_chunks: number | null
  chunk_size: number | null
  rows_processed: number
  total_rows: number | null
  rows_remaining: number | null
  rows_changed: number
  rows_uploaded: number
  rows_inserted: number
  rows_updated: number
  speed_rows_sec: number
  eta_seconds: number | null
  progress_pct: number
  started_at: string | null
  updated_at: string | null
}

export interface TableStat {
  table_name: string
  sync_mode: string
  source_rows: number | null
  ho_rows: number
  changed_today: number
  examined_today: number
  uploaded_today: number
  inserted_today: number
  updated_today: number
  skipped_today: number
  last_sync: string | null
  watermark_column: string | null
  last_business_value: string | null
}

export interface ChunkStatusRow {
  chunk_execution_id: number
  table_name: string
  chunk_no: number
  chunk_status: string
  rows_processed: number
  started_at: string | null
  completed_at: string | null
  error_message: string | null
}

export interface RegistryPopulateResult {
  status: string
  tables_discovered: number
  new_tables: number
  existing_tables: number
  total_registry_tables: number
}

export interface TablePromoteResult {
  status: string
  registry_tables: number
  promoted_tables: number
  existing_tables: number
  total_master_tables: number
}
