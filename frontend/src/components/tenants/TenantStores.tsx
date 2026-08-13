import type { TenantStore } from '../../types/store'
import { EmptyState } from '../common/EmptyState'
import { ErrorState } from '../common/ErrorState'
import { TableSkeleton } from '../common/TableSkeleton'
import { DataTable, type DataTableColumn } from '../common/DataTable'

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
  const columns: DataTableColumn<TenantStore>[] = [
    { key: 'store_code', header: 'Store Code', sortable: true },
    {
      key: 'store_name',
      header: 'Store Name',
      sortable: true,
      accessor: (store) => <span className="fw-medium">{store.store_name}</span>,
    },
  ]

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
    <DataTable
      columns={columns}
      data={stores}
      getRowId={(store) => store.store_id}
      pageSize={10}
    />
  )
}
