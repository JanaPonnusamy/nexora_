import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { PageHeader } from '../../components/common/PageHeader'
import { EmptyState } from '../../components/common/EmptyState'
import { ErrorState } from '../../components/common/ErrorState'
import { TableSkeleton } from '../../components/common/TableSkeleton'
import { StoreToolbar } from '../../components/stores/StoreToolbar'
import type { StatusFilter } from '../../components/tenants/TenantToolbar'
import { StoreTable } from '../../components/stores/StoreTable'
import { StoreCardList } from '../../components/stores/StoreCardList'
import { StoreFormModal } from '../../components/stores/StoreFormModal'
import { useStores } from '../../hooks/useStores'
import { useTenants } from '../../hooks/useTenants'
import type { Store } from '../../types/store'

type ModalState = { mode: 'create' } | { mode: 'edit'; store: Store } | null

export default function StoresPage() {
  const navigate = useNavigate()
  const { stores, isLoading, error, reload } = useStores()
  const { tenants } = useTenants()
  const [search, setSearch] = useState('')
  const [tenantFilter, setTenantFilter] = useState('all')
  const [status, setStatus] = useState<StatusFilter>('all')
  const [modal, setModal] = useState<ModalState>(null)

  const tenantNames = useMemo(
    () => new Map(tenants.map((tenant) => [tenant.tenant_id, tenant.tenant_name])),
    [tenants],
  )
  const getTenantName = (tenantId: string) => tenantNames.get(tenantId) ?? '—'

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase()
    return stores.filter((store) => {
      if (status === 'active' && !store.is_active) return false
      if (status === 'inactive' && store.is_active) return false
      if (tenantFilter !== 'all' && store.tenant_id !== tenantFilter) return false
      if (!query) return true
      return [
        store.store_code,
        store.store_name,
        store.server_name,
        store.database_name,
        getTenantName(store.tenant_id),
      ].some((value) => value.toLowerCase().includes(query))
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stores, search, status, tenantFilter, tenantNames])

  const openWorkspace = (store: Store, tab?: 'users' | 'roles') =>
    navigate(`/platform/stores/${store.store_id}${tab ? `?tab=${tab}` : ''}`)

  const renderContent = () => {
    if (isLoading) {
      return <TableSkeleton rows={6} columns={6} />
    }
    if (error) {
      return <ErrorState description={error} onRetry={reload} />
    }
    if (stores.length === 0) {
      return (
        <EmptyState
          icon="bi-shop"
          title="No stores yet"
          description="Create your first store to get started."
          action={{ label: 'Add Store', icon: 'bi-plus-lg', onClick: () => setModal({ mode: 'create' }) }}
        />
      )
    }
    if (filtered.length === 0) {
      return (
        <EmptyState
          icon="bi-search"
          title="No matching stores"
          description="Try adjusting your search or filters."
        />
      )
    }
    return (
      <>
        <StoreTable
          stores={filtered}
          getTenantName={getTenantName}
          onView={(store) => openWorkspace(store)}
          onEdit={(store) => setModal({ mode: 'edit', store })}
          onUsers={(store) => openWorkspace(store, 'users')}
          onRoles={(store) => openWorkspace(store, 'roles')}
        />
        <StoreCardList
          stores={filtered}
          getTenantName={getTenantName}
          onView={(store) => openWorkspace(store)}
          onEdit={(store) => setModal({ mode: 'edit', store })}
          onUsers={(store) => openWorkspace(store, 'users')}
          onRoles={(store) => openWorkspace(store, 'roles')}
        />
      </>
    )
  }

  return (
    <div className="container-fluid px-0">
      <PageHeader title="Stores" breadcrumb={['Platform', 'Stores']} />
      <StoreToolbar
        search={search}
        onSearchChange={setSearch}
        tenantFilter={tenantFilter}
        onTenantFilterChange={setTenantFilter}
        status={status}
        onStatusChange={setStatus}
        tenants={tenants}
        onAdd={() => setModal({ mode: 'create' })}
      />
      {renderContent()}
      {modal && (
        <StoreFormModal
          mode={modal.mode}
          store={modal.mode === 'edit' ? modal.store : undefined}
          tenants={tenants}
          onClose={() => setModal(null)}
          onSaved={() => {
            setModal(null)
            void reload()
          }}
        />
      )}
    </div>
  )
}
