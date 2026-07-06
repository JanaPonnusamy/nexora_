import { useAsyncData } from '../../hooks/useAsyncData'
import { syncService } from '../../services/syncService'
import { DonutChart } from '../dashboard/DonutChart'
import { Skeleton } from '../common/Skeleton'
import { ErrorState } from '../common/ErrorState'

export function StoreHealthSummaryCard() {
  const { data, isLoading, error, reload } = useAsyncData(syncService.storeHealth)

  const online = data?.filter((store) => store.agent_status === 'Online').length ?? 0
  const offline = (data?.length ?? 0) - online

  return (
    <div className="card h-100">
      <div className="card-body">
        <div className="dashboard-panel__title">Store Health</div>
        {isLoading ? (
          <Skeleton height="7rem" />
        ) : error || !data ? (
          <ErrorState description={error ?? 'Failed to load store health'} onRetry={reload} />
        ) : (
          <DonutChart
            segments={[
              { label: 'Online', value: online, color: 'var(--bs-success)' },
              { label: 'Offline', value: offline, color: 'var(--bs-secondary)' },
            ]}
          />
        )}
      </div>
    </div>
  )
}
