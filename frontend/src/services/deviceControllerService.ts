import { api } from './apiClient'
import type {
  DcCommand,
  DcDevice,
  DcDeviceDetail,
  DcEnrollCode,
  DcMeta,
  DcPackage,
  DcTerminalRow,
  DcTerminalSession,
} from '../types/deviceController'

const BASE = '/api/device-controller'

// Nexora Device Controller (super-admin only server side): fleet control,
// signed per-app commands, enrollment codes and the remote terminal.
export const deviceControllerService = {
  meta: () => api.get<DcMeta>(`${BASE}/meta`),
  devices: () => api.get<{ devices: DcDevice[] }>(`${BASE}/devices`),
  device: (id: string) => api.get<DcDeviceDetail>(`${BASE}/devices/${id}`),
  revokeDevice: (id: string) => api.post<{ revoked: boolean }>(`${BASE}/devices/${id}/revoke`, {}),

  command: (deviceId: string, appKey: string, action: string, args: Record<string, unknown> = {}) =>
    api.post<DcCommand>(`${BASE}/devices/${deviceId}/commands`, { app_key: appKey, action, args }),
  bulkCommand: (deviceIds: string[], appKey: string, action: string, args: Record<string, unknown> = {}) =>
    api.post<{ results: { device_id: string; ok: boolean; error?: string }[] }>(
      `${BASE}/commands/bulk`, { device_ids: deviceIds, app_key: appKey, action, args },
    ),
  cancelCommand: (id: string) => api.post<DcCommand>(`${BASE}/commands/${id}/cancel`, {}),

  packages: () =>
    api.get<{ packages: Partial<Record<string, DcPackage[]>>; has_command_key: boolean }>(`${BASE}/packages`),

  enrollCodes: () => api.get<{ codes: DcEnrollCode[] }>(`${BASE}/enroll-codes`),
  createEnrollCode: (note: string, hours: number, maxUses: number) =>
    api.post<DcEnrollCode>(`${BASE}/enroll-codes`, { note, hours, max_uses: maxUses }),
  revokeEnrollCode: (code: string) => api.post<{ revoked: boolean }>(`${BASE}/enroll-codes/${code}/revoke`, {}),

  terminals: (activeOnly = false, deviceId?: string) => {
    const q = new URLSearchParams()
    if (activeOnly) q.set('active', 'true')
    if (deviceId) q.set('device_id', deviceId)
    return api.get<{ sessions: DcTerminalSession[] }>(`${BASE}/terminals?${q.toString()}`)
  },
  openTerminal: (deviceId: string) => api.post<DcTerminalSession>(`${BASE}/terminals`, { device_id: deviceId }),
  terminalInput: (sessionId: string, data: string) =>
    api.post<{ seq: number }>(`${BASE}/terminals/${sessionId}/input`, { data }),
  terminalReset: (sessionId: string) => api.post<{ ok: boolean }>(`${BASE}/terminals/${sessionId}/reset`, {}),
  closeTerminal: (sessionId: string) => api.post<DcTerminalSession>(`${BASE}/terminals/${sessionId}/close`, {}),
  terminalOutput: (sessionId: string, after: number, wait: number, signal?: AbortSignal) =>
    api.get<{ rows: DcTerminalRow[]; status: DcTerminalSession['status'] }>(
      `${BASE}/terminals/${sessionId}/output?after=${after}&wait=${wait}`,
      { signal, timeoutMs: (wait + 20) * 1000 },
    ),
}
