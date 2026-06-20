import type { TenantStore } from '../../types/store'
import { EmptyState } from '../common/EmptyState'
import { ErrorState } from '../common/ErrorState'
import { TableSkeleton } from '../common/TableSkeleton'

interface TenantStoresProps {
  stores: TenantStore[]
  isLoading: boolean
  error: string | null
  onRetry: () => void
  onCreateStore: () => void
}

export function TenantStores({
  stores,
  isLoading,
  error,
  onRetry,
  onCreateStore,
}: TenantStoresProps) {
  if (isLoading) {
    return <TableSkeleton rows={4} columns={2} />
  }
  if (error) {
    return <ErrorState description={error} onRetry={onRetry} />
  }
  if (stores.length === 0) {
    return (
      <EmptyState
        icon="bi-shop"
        title="No Stores Found"
        description="This tenant has no stores yet."
        action={{ label: 'Create Store', icon: 'bi-plus-lg', onClick: onCreateStore }}
      />
    )
  }

  return (
    <div className="table-responsive">
      <table className="table table-hover align-middle data-table">
        <thead>
          <tr>
            <th scope="col">Store Code</th>
            <th scope="col">Store Name</th>
          </tr>
        </thead>
        <tbody>
          {stores.map((store) => (
            <tr key={store.store_id}>
              <td>{store.store_code}</td>
              <td className="fw-medium">{store.store_name}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
