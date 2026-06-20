import { useEffect, useState } from 'react'
import { PageHeader } from '../../components/common/PageHeader'
import { EmptyState } from '../../components/common/EmptyState'
import { ErrorState } from '../../components/common/ErrorState'
import { TableSkeleton } from '../../components/common/TableSkeleton'
import { usePermissionMatrix } from '../../hooks/usePermissionMatrix'
import { permissionService } from '../../services/permissionService'

const cellKey = (roleId: string, moduleId: string) => `${roleId}:${moduleId}`

export default function PermissionsPage() {
  const { matrix, isLoading, error, reload } = usePermissionMatrix()
  const [assigned, setAssigned] = useState<Set<string>>(new Set())
  const [busy, setBusy] = useState<Set<string>>(new Set())
  const [actionError, setActionError] = useState<string | null>(null)

  useEffect(() => {
    if (matrix) {
      setAssigned(new Set(matrix.assignments.map((a) => cellKey(a.role_id, a.module_id))))
    }
  }, [matrix])

  const toggle = async (roleId: string, moduleId: string) => {
    const key = cellKey(roleId, moduleId)
    if (busy.has(key)) return
    const currentlyAssigned = assigned.has(key)

    setAssigned((prev) => {
      const next = new Set(prev)
      if (currentlyAssigned) next.delete(key)
      else next.add(key)
      return next
    })
    setBusy((prev) => new Set(prev).add(key))
    setActionError(null)

    try {
      if (currentlyAssigned) {
        await permissionService.remove(roleId, moduleId)
      } else {
        await permissionService.assign(roleId, moduleId)
      }
    } catch (err) {
      setAssigned((prev) => {
        const next = new Set(prev)
        if (currentlyAssigned) next.add(key)
        else next.delete(key)
        return next
      })
      setActionError(err instanceof Error ? err.message : 'Failed to update assignment')
    } finally {
      setBusy((prev) => {
        const next = new Set(prev)
        next.delete(key)
        return next
      })
    }
  }

  const renderContent = () => {
    if (isLoading) {
      return <TableSkeleton rows={6} columns={4} />
    }
    if (error || !matrix) {
      return <ErrorState description={error ?? 'Failed to load permission matrix'} onRetry={reload} />
    }
    if (matrix.roles.length === 0 || matrix.modules.length === 0) {
      return (
        <EmptyState
          icon="bi-grid-3x3-gap"
          title="Nothing to assign yet"
          description="Active roles and modules are required to manage permissions."
        />
      )
    }

    return (
      <>
        {actionError && <div className="alert alert-danger py-2">{actionError}</div>}
        <div className="table-responsive">
          <table className="table align-middle data-table permission-matrix">
            <thead>
              <tr>
                <th scope="col" className="permission-matrix__corner">Module</th>
                {matrix.roles.map((role) => (
                  <th scope="col" key={role.role_id} className="text-center">
                    {role.role_name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {matrix.modules.map((module) => (
                <tr key={module.module_id}>
                  <th scope="row" className="permission-matrix__module">
                    <div className="fw-medium">{module.module_name}</div>
                    <code className="small">{module.module_code}</code>
                  </th>
                  {matrix.roles.map((role) => {
                    const key = cellKey(role.role_id, module.module_id)
                    const isAssigned = assigned.has(key)
                    const isBusy = busy.has(key)
                    return (
                      <td key={role.role_id} className="text-center">
                        <button
                          type="button"
                          className={`btn btn-sm permission-cell ${isAssigned ? 'btn-success' : 'btn-outline-secondary'}`}
                          aria-pressed={isAssigned}
                          aria-label={`${isAssigned ? 'Unassign' : 'Assign'} ${module.module_name} for ${role.role_name}`}
                          disabled={isBusy}
                          onClick={() => toggle(role.role_id, module.module_id)}
                        >
                          {isBusy ? (
                            <span className="spinner-border spinner-border-sm" aria-hidden="true" />
                          ) : (
                            <i
                              className={`bi ${isAssigned ? 'bi-check-lg' : 'bi-x-lg'}`}
                              aria-hidden="true"
                            />
                          )}
                        </button>
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </>
    )
  }

  return (
    <div className="container-fluid px-0">
      <PageHeader title="Permissions" breadcrumb={['Administration', 'Permissions']} />
      {renderContent()}
    </div>
  )
}
