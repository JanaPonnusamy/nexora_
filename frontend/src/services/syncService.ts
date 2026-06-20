import { api } from './apiClient'
import type {
  CatalogTable,
  ControlCenter,
  StoreHealthRow,
  SyncHistoryRow,
  SyncSchedule,
  SyncTable,
  SyncTableInput,
  TableColumns,
} from '../types/sync'

export const syncService = {
  controlCenter: () => api.get<ControlCenter>('/api/sync/control-center'),
  schedules: () => api.get<SyncSchedule[]>('/api/sync/schedules'),
  storeHealth: () => api.get<StoreHealthRow[]>('/api/sync/store-health'),
  history: () => api.get<SyncHistoryRow[]>('/api/sync/history'),
  catalogTables: (search: string) =>
    api.get<CatalogTable[]>(
      `/api/sync/catalog/tables${search ? `?search=${encodeURIComponent(search)}` : ''}`,
    ),
  tables: () => api.get<SyncTable[]>('/api/sync/tables'),
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
}
