import { api } from './apiClient'
import type { DbMonitorKillResult, DbMonitorRequest, DbMonitorSession } from '../types/legacyOrder'

const BASE = '/api/db-monitor'

/** Live Queries / Repair: currently-executing requests on central OrderNMC,
 *  plus a KILL action. Platform-admin only (server-gated). */
export const dbMonitorService = {
  activeRequests: () => api.get<{ requests: DbMonitorRequest[] }>(`${BASE}/requests`),
  allSessions: () => api.get<{ sessions: DbMonitorSession[] }>(`${BASE}/sessions`),
  killSession: (sessionId: number) =>
    api.post<DbMonitorKillResult>(`${BASE}/kill`, { session_id: sessionId }),
}
