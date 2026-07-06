import { api } from './apiClient'
import type {
  AvailableTable,
  CatalogTable,
  ChunkStatusRow,
  ControlCenter,
  LiveStore,
  PendingTask,
  TableStat,
  RegistryPopulateResult,
  ScheduleInput,
  StoreHealthRow,
  SyncHistoryRow,
  SyncSchedule,
  SyncTable,
  SyncTableInput,
  SyncTaskResult,
  TableColumns,
  TablePromoteResult,
} from '../types/sync'

export const syncService = {
  controlCenter: () => api.get<ControlCenter>('/api/sync/control-center'),
  schedules: () => api.get<SyncSchedule[]>('/api/sync/schedules'),
  createSchedule: (body: ScheduleInput) =>
    api.post<SyncSchedule>('/api/sync/schedules', body),
  updateSchedule: (scheduleId: number, body: ScheduleInput) =>
    api.put<SyncSchedule>(`/api/sync/schedules/${scheduleId}`, body),
  setScheduleStatus: (scheduleId: number, isEnabled: boolean) =>
    api.patch<SyncSchedule>(`/api/sync/schedules/${scheduleId}/status`, { is_enabled: isEnabled }),
  suspendSchedule: (scheduleId: number, suspendedUntil: string | null) =>
    api.patch<SyncSchedule>(`/api/sync/schedules/${scheduleId}/suspend`, { suspended_until: suspendedUntil }),
  deleteSchedule: (scheduleId: number) =>
    api.delete<void>(`/api/sync/schedules/${scheduleId}`),
  seedSchedules: () =>
    api.post<{ created: number; stores: number }>('/api/sync/schedules/seed', {}),
  storeHealth: () => api.get<StoreHealthRow[]>('/api/sync/store-health'),
  history: () => api.get<SyncHistoryRow[]>('/api/sync/history'),
  catalogTables: (search: string) =>
    api.get<CatalogTable[]>(
      `/api/sync/catalog/tables${search ? `?search=${encodeURIComponent(search)}` : ''}`,
    ),
  tables: () => api.get<SyncTable[]>('/api/sync/tables'),
  availableTables: (search: string) =>
    api.get<AvailableTable[]>(
      `/api/sync/tables/available${search ? `?search=${encodeURIComponent(search)}` : ''}`,
    ),
  populateRegistry: () =>
    api.post<RegistryPopulateResult>('/api/sync/table-registry/populate', {}),
  promoteTables: () => api.post<TablePromoteResult>('/api/sync/table-master/promote', {}),
  createTable: (input: SyncTableInput) => api.post<SyncTable>('/api/sync/tables', input),
  updateTable: (syncTableId: string, input: SyncTableInput) =>
    api.put<SyncTable>(`/api/sync/tables/${syncTableId}`, input),
  setTableStatus: (syncTableId: string, isActive: boolean) =>
    api.patch<SyncTable>(`/api/sync/tables/${syncTableId}/status`, { is_active: isActive }),
  tableColumns: (syncTableId: string) =>
    api.get<TableColumns>(`/api/sync/tables/${syncTableId}/columns`),
  saveMapping: (body: {
    sync_table_id: string
    table_name: string
    column_name: string
    data_type: string
    is_selected: boolean
    is_pk: boolean
    is_hash: boolean
    is_watermark: boolean
    column_order: number
  }) => api.put('/api/sync/mappings', body),
  createTask: (body: {
    tenant_id: string
    store_id: string
    execution_type?: string
    sync_mode?: string
    total_tables?: number
  }) => api.post<SyncTaskResult>('/api/sync/tasks/create', body),
  pendingTasks: (storeId: string) =>
    api.get<PendingTask[]>(`/api/sync/tasks/pending/${storeId}`),
  startTask: (taskId: string) =>
    api.post<SyncTaskResult>(`/api/sync/tasks/${taskId}/start`, {}),
  completeTask: (taskId: string) =>
    api.post<SyncTaskResult>(`/api/sync/tasks/${taskId}/complete`, {}),
  failTask: (taskId: string, message: string) =>
    api.post<SyncTaskResult>(`/api/sync/tasks/${taskId}/fail`, { message }),
  chunkStatus: (executionId: string) =>
    api.get<ChunkStatusRow[]>(`/api/sync/chunks/status/${executionId}`),
  live: () => api.get<LiveStore[]>('/api/sync/live'),
  tableStats: () => api.get<TableStat[]>('/api/sync/table-stats'),
  control: (storeIds: string[], action: 'PAUSE' | 'STOP') =>
    api.post<{ affected: number; action: string }>('/api/sync/control', {
      store_ids: storeIds,
      action,
    }),
}
