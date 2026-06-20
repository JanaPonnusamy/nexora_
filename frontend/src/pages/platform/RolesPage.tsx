import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { PageHeader } from '../../components/common/PageHeader'
import { EmptyState } from '../../components/common/EmptyState'
import { ErrorState } from '../../components/common/ErrorState'
import { TableSkeleton } from '../../components/common/TableSkeleton'
import { RoleToolbar } from '../../components/roles/RoleToolbar'
import type { StatusFilter } from '../../components/tenants/TenantToolbar'
import { RoleTable } from '../../components/roles/RoleTable'
import { RoleCardList } from '../../components/roles/RoleCardList'
import { RoleFormModal } from '../../components/roles/RoleFormModal'
import { useRoles } from '../../hooks/useRoles'
import type { Role } from '../../types/role'

type ModalState = { mode: 'create' } | { mode: 'edit'; role: Role } | null

export default function RolesPage() {
  const navigate = useNavigate()
  const { roles, isLoading, error, reload } = useRoles()
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<StatusFilter>('all')
  const [modal, setModal] = useState<ModalState>(null)

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase()
    return roles.filter((role) => {
      if (status === 'active' && !role.is_active) return false
      if (status === 'inactive' && role.is_active) return false
      if (!query) return true
      return [role.role_name, role.description ?? ''].some((value) =>
        value.toLowerCase().includes(query),
      )
    })
  }, [roles, search, status])

  const openWorkspace = (role: Role, tab?: 'users') =>
    navigate(`/platform/roles/${role.role_id}${tab ? `?tab=${tab}` : ''}`)

  const renderContent = () => {
    if (isLoading) {
      return <TableSkeleton rows={6} columns={4} />
    }
    if (error) {
      return <ErrorState description={error} onRetry={reload} />
    }
    if (roles.length === 0) {
      return (
        <EmptyState
          icon="bi-person-badge"
          title="No roles yet"
          description="Create your first role to get started."
          action={{ label: 'Add Role', icon: 'bi-plus-lg', onClick: () => setModal({ mode: 'create' }) }}
        />
      )
    }
    if (filtered.length === 0) {
      return (
        <EmptyState
          icon="bi-search"
          title="No matching roles"
          description="Try adjusting your search or status filter."
        />
      )
    }
    return (
      <>
        <RoleTable
          roles={filtered}
          onView={(role) => openWorkspace(role)}
          onEdit={(role) => setModal({ mode: 'edit', role })}
          onUsers={(role) => openWorkspace(role, 'users')}
        />
        <RoleCardList
          roles={filtered}
          onView={(role) => openWorkspace(role)}
          onEdit={(role) => setModal({ mode: 'edit', role })}
          onUsers={(role) => openWorkspace(role, 'users')}
        />
      </>
    )
  }

  return (
    <div className="container-fluid px-0">
      <PageHeader title="Roles" breadcrumb={['Platform', 'Roles']} />
      <RoleToolbar
        search={search}
        onSearchChange={setSearch}
        status={status}
        onStatusChange={setStatus}
        onAdd={() => setModal({ mode: 'create' })}
      />
      {renderContent()}
      {modal && (
        <RoleFormModal
          mode={modal.mode}
          role={modal.mode === 'edit' ? modal.role : undefined}
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
