import { useAsyncData } from '../../hooks/useAsyncData'
import { api } from '../../services/apiClient'
import { Skeleton } from '../common/Skeleton'

interface SystemStatus {
  apiStatus: string
  dbStatus: string
}

async function fetchSystemStatus(): Promise<SystemStatus> {
  const [health, db] = await Promise.all([
    api.get<{ status: string }>('/health'),
    api.get<{ status: string; database?: string }>('/health/db'),
  ])
  return { apiStatus: health.status, dbStatus: db.status }
}

function StatusRow({ label, ok, text }: { label: string; ok: boolean; text: string }) {
  return (
    <div className="activity-feed__item">
      <span className={`badge ${ok ? 'text-bg-success' : 'text-bg-danger'}`}>
        <i className={`bi ${ok ? 'bi-check-circle' : 'bi-exclamation-triangle'} me-1`} aria-hidden="true" />
        {text}
      </span>
      <span>{label}</span>
    </div>
  )
}

export function SystemStatusCard() {
  const { data, isLoading, error } = useAsyncData(fetchSystemStatus)

  return (
    <div className="card h-100">
      <div className="card-body">
        <div className="dashboard-panel__title">System Status</div>
        {isLoading ? (
          <Skeleton height="3rem" />
        ) : error || !data ? (
          <StatusRow label="Platform API" ok={false} text="Unreachable" />
        ) : (
          <div className="activity-feed">
            <StatusRow label="Platform API" ok={data.apiStatus === 'healthy'} text={data.apiStatus === 'healthy' ? 'Healthy' : 'Down'} />
            <StatusRow label="Database" ok={data.dbStatus === 'healthy'} text={data.dbStatus === 'healthy' ? 'Connected' : 'Disconnected'} />
          </div>
        )}
      </div>
    </div>
  )
}
