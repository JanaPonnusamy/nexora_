import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { PageHeader } from '../../components/common/PageHeader'
import { EmptyState } from '../../components/common/EmptyState'
import { ErrorState } from '../../components/common/ErrorState'
import { TableSkeleton } from '../../components/common/TableSkeleton'
import { UserToolbar } from '../../components/users/UserToolbar'
import type { StatusFilter } from '../../components/tenants/TenantToolbar'
import { UserTable } from '../../components/users/UserTable'
import { UserCardList } from '../../components/users/UserCardList'
import { UserFormModal } from '../../components/users/UserFormModal'
import { useUsers } from '../../hooks/useUsers'
import { useTenants } from '../../hooks/useTenants'
import { useStores } from '../../hooks/useStores'
import { useRoles } from '../../hooks/useRoles'
import type { User } from '../../types/user'

type ModalState = { mode: 'create' } | { mode: 'edit'; user: User } | null

export default function UsersPage() {
  const navigate = useNavigate()
  const { tenants } = useTenants()
  const { stores } = useStores()
  const { roles } = useRoles()

  const [search, setSearch] = useState('')
  const [tenantFilter, setTenantFilter] = useState('all')
  const [storeFilter, setStoreFilter] = useState('all')
  const [roleFilter, setRoleFilter] = useState('all')
  const [status, setStatus] = useState<StatusFilter>('all')
  const [modal, setModal] = useState<ModalState>(null)

  const { users, isLoading, error, reload } = useUsers({
    tenantId: tenantFilter !== 'all' ? tenantFilter : undefined,
    storeId: storeFilter !== 'all' ? storeFilter : undefined,
    roleId: roleFilter !== 'all' ? roleFilter : undefined,
    status: status !== 'all' ? status : undefined,
  })

  const availableStores = useMemo(
    () => (tenantFilter === 'all' ? stores : stores.filter((store) => store.tenant_id === tenantFilter)),
    [stores, tenantFilter],
  )

  const handleTenantChange = (value: string) => {
    setTenantFilter(value)
    setStoreFilter('all')
  }

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase()
    if (!query) return users
    return users.filter((user) =>
      [user.username, user.full_name].some((value) => value.toLowerCase().includes(query)),
    )
  }, [users, search])

  const openWorkspace = (user: User, tab?: 'roles' | 'stores') =>
    navigate(`/platform/users/${user.user_id}${tab ? `?tab=${tab}` : ''}`)

  const renderContent = () => {
    if (isLoading) {
      return <TableSkeleton rows={6} columns={6} />
    }
    if (error) {
      return <ErrorState description={error} onRetry={reload} />
    }
    if (users.length === 0) {
      return (
        <EmptyState
          icon="bi-people"
          title="No users yet"
          description="Create your first user to get started."
          action={{ label: 'Add User', icon: 'bi-plus-lg', onClick: () => setModal({ mode: 'create' }) }}
        />
      )
    }
    if (filtered.length === 0) {
      return (
        <EmptyState
          icon="bi-search"
          title="No matching users"
          description="Try adjusting your search or filters."
        />
      )
    }
    return (
      <>
        <UserTable
          users={filtered}
          onView={(user) => openWorkspace(user)}
          onEdit={(user) => setModal({ mode: 'edit', user })}
          onRoles={(user) => openWorkspace(user, 'roles')}
          onStores={(user) => openWorkspace(user, 'stores')}
        />
        <UserCardList
          users={filtered}
          onView={(user) => openWorkspace(user)}
          onEdit={(user) => setModal({ mode: 'edit', user })}
          onRoles={(user) => openWorkspace(user, 'roles')}
          onStores={(user) => openWorkspace(user, 'stores')}
        />
      </>
    )
  }

  return (
    <div className="container-fluid px-0">
      <PageHeader title="Users" breadcrumb={['Platform', 'Users']} />
      <UserToolbar
        search={search}
        onSearchChange={setSearch}
        tenantFilter={tenantFilter}
        onTenantFilterChange={handleTenantChange}
        storeFilter={storeFilter}
        onStoreFilterChange={setStoreFilter}
        roleFilter={roleFilter}
        onRoleFilterChange={setRoleFilter}
        status={status}
        onStatusChange={setStatus}
        tenants={tenants}
        stores={availableStores}
        roles={roles}
        onAdd={() => setModal({ mode: 'create' })}
      />
      {renderContent()}
      {modal && (
        <UserFormModal
          mode={modal.mode}
          user={modal.mode === 'edit' ? modal.user : undefined}
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
