import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { PageHeader } from '../../components/common/PageHeader'
import { EmptyState } from '../../components/common/EmptyState'
import { ErrorState } from '../../components/common/ErrorState'
import { TableSkeleton } from '../../components/common/TableSkeleton'
import { ModuleToolbar } from '../../components/modules/ModuleToolbar'
import type { StatusFilter } from '../../components/tenants/TenantToolbar'
import { ModuleTable } from '../../components/modules/ModuleTable'
import { ModuleCardList } from '../../components/modules/ModuleCardList'
import { ModuleFormModal } from '../../components/modules/ModuleFormModal'
import { useModules } from '../../hooks/useModules'
import type { Module } from '../../types/module'

type ModalState = { mode: 'create' } | { mode: 'edit'; module: Module } | null

export default function ModulesPage() {
  const navigate = useNavigate()
  const { modules, isLoading, error, reload } = useModules()
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<StatusFilter>('all')
  const [modal, setModal] = useState<ModalState>(null)

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase()
    return modules.filter((module) => {
      if (status === 'active' && !module.is_active) return false
      if (status === 'inactive' && module.is_active) return false
      if (!query) return true
      return [module.module_code, module.module_name, module.description ?? ''].some((value) =>
        value.toLowerCase().includes(query),
      )
    })
  }, [modules, search, status])

  const openWorkspace = (module: Module) =>
    navigate(`/administration/modules/${module.module_id}`)

  const renderContent = () => {
    if (isLoading) {
      return <TableSkeleton rows={6} columns={4} />
    }
    if (error) {
      return <ErrorState description={error} onRetry={reload} />
    }
    if (modules.length === 0) {
      return (
        <EmptyState
          icon="bi-boxes"
          title="No modules yet"
          description="Create your first module to get started."
          action={{ label: 'Add Module', icon: 'bi-plus-lg', onClick: () => setModal({ mode: 'create' }) }}
        />
      )
    }
    if (filtered.length === 0) {
      return (
        <EmptyState
          icon="bi-search"
          title="No matching modules"
          description="Try adjusting your search or status filter."
        />
      )
    }
    return (
      <>
        <ModuleTable
          modules={filtered}
          onView={(module) => openWorkspace(module)}
          onEdit={(module) => setModal({ mode: 'edit', module })}
        />
        <ModuleCardList
          modules={filtered}
          onView={(module) => openWorkspace(module)}
          onEdit={(module) => setModal({ mode: 'edit', module })}
        />
      </>
    )
  }

  return (
    <div className="container-fluid px-0">
      <PageHeader title="Modules" breadcrumb={['Administration', 'Modules']} />
      <ModuleToolbar
        search={search}
        onSearchChange={setSearch}
        status={status}
        onStatusChange={setStatus}
        onAdd={() => setModal({ mode: 'create' })}
      />
      {renderContent()}
      {modal && (
        <ModuleFormModal
          mode={modal.mode}
          module={modal.mode === 'edit' ? modal.module : undefined}
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
