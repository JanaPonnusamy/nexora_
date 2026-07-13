import { api } from './apiClient'
import type {
  LegacyJob,
  LegacyStore,
  LegacyTable,
  OrderMode,
  OrderRow,
} from '../types/legacyOrder'

const BASE = '/api/legacy-order'

export const legacyOrderService = {
  listStores: (activeOnly = true) =>
    api.get<LegacyStore[]>(`${BASE}/stores?active_only=${activeOnly}`),

  listTables: () => api.get<LegacyTable[]>(`${BASE}/tables`),

  defaults: () => api.get<{ min_days: number; max_days: number }>(`${BASE}/defaults`),

  startSync: (storeName: string, tables?: string[]) =>
    api.post<{ job_id: string }>(`${BASE}/sync`, {
      store_name: storeName,
      tables: tables ?? null,
    }),

  startOrderProcess: (
    storeName: string,
    minDays: number,
    maxDays: number,
    mode: OrderMode,
  ) =>
    api.post<{ job_id: string }>(`${BASE}/order-process`, {
      store_name: storeName,
      min_days: minDays,
      max_days: maxDays,
      mode,
    }),

  getJob: (jobId: string) => api.get<LegacyJob>(`${BASE}/jobs/${jobId}`),

  orders: (storeName: string) =>
    api.get<OrderRow[]>(`${BASE}/orders/${encodeURIComponent(storeName)}`),
}
