import { api } from './apiClient'

/** Generic per-user grid display settings — column order/width/padding for
 *  ANY grid, keyed by an arbitrary grid_key string. One backend table
 *  (dbo.user_grid_settings) serves every grid; adding a new grid never
 *  needs new backend work, just a new key. */
export interface GridSettingsPayload {
  columnOrder: string[]
  columnWidths: Record<string, number>
  padding: number
}

export interface GridSettingsResponse {
  grid_key: string
  settings: GridSettingsPayload | null
  updated_at: string | null
}

export const gridSettingsService = {
  get: (gridKey: string) => api.get<GridSettingsResponse>(`/api/grid-settings/${gridKey}`),
  save: (gridKey: string, settings: GridSettingsPayload) =>
    api.put<GridSettingsResponse>(`/api/grid-settings/${gridKey}`, { settings }),
  reset: (gridKey: string) => api.delete<{ ok: boolean }>(`/api/grid-settings/${gridKey}`),
}
