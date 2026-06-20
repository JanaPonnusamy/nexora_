import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { PageHeader } from '../../components/common/PageHeader'
import { EmptyState } from '../../components/common/EmptyState'
import { ErrorState } from '../../components/common/ErrorState'
import { TableSkeleton } from '../../components/common/TableSkeleton'
import { TenantToolbar } from '../../components/tenants/TenantToolbar'
import type { StatusFilter } from '../../components/tenants/TenantToolbar'
import { TenantTable } from '../../components/tenants/TenantTable'
import { TenantCardList } from '../../components/tenants/TenantCardList'
import { TenantFormModal } from '../../components/tenants/TenantFormModal'
import { useTenants } from '../../hooks/useTenants'
import type { Tenant } from '../../types/tenant'

type ModalState = { mode: 'create' } | { mode: 'edit'; tenant: Tenant } | null

export default function TenantsPage() {
  const navigate = useNavigate()
  const { tenants, isLoading, error, reload } = useTenants()
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<StatusFilter>('all')
  const [modal, setModal] = useState<ModalState>(null)

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase()
    return tenants.filter((tenant) => {
      if (status === 'active' && !tenant.is_active) return false
      if (status === 'inactive' && tenant.is_active) return false
      if (!query) return true
      return [
        tenant.tenant_code,
        tenant.tenant_abbreviation,
        tenant.tenant_name,
        tenant.db_name,
      ].some((value) => value.toLowerCase().includes(query))
    })
  }, [tenants, search, status])

  const openWorkspace = (tenant: Tenant, tab?: 'stores' | 'users') =>
    navigate(`/platform/tenants/${tenant.tenant_id}${tab ? `?tab=${tab}` : ''}`)

  const renderContent = () => {
    if (isLoading) {
      return <TableSkeleton rows={6} columns={5} />
    }
    if (error) {
      return <ErrorState description={error} onRetry={reload} />
    }
    if (tenants.length === 0) {
      return (
        <EmptyState
          icon="bi-building"
          title="No tenants yet"
          description="Create your first tenant to get started."
        />
      )
    }
    if (filtered.length === 0) {
      return (
        <EmptyState
          icon="bi-search"
          title="No matching tenants"
          description="Try adjusting your search or status filter."
        />
      )
    }
    return (
      <>
        <TenantTable
          tenants={filtered}
          onView={(tenant) => openWorkspace(tenant)}
          onEdit={(tenant) => setModal({ mode: 'edit', tenant })}
          onStores={(tenant) => openWorkspace(tenant, 'stores')}
          onUsers={(tenant) => openWorkspace(tenant, 'users')}
        />
        <TenantCardList
          tenants={filtered}
          onView={(tenant) => openWorkspace(tenant)}
          onEdit={(tenant) => setModal({ mode: 'edit', tenant })}
          onStores={(tenant) => openWorkspace(tenant, 'stores')}
          onUsers={(tenant) => openWorkspace(tenant, 'users')}
        />
      </>
    )
  }

  return (
    <div className="container-fluid px-0">
      <PageHeader title="Tenants" breadcrumb={['Platform', 'Tenants']} />
      <TenantToolbar
        search={search}
        onSearchChange={setSearch}
        status={status}
        onStatusChange={setStatus}
        onAdd={() => setModal({ mode: 'create' })}
      />
      {renderContent()}
      {modal && (
        <TenantFormModal
          mode={modal.mode}
          tenant={modal.mode === 'edit' ? modal.tenant : undefined}
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
