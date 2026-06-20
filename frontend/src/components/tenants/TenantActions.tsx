import type { MouseEvent } from 'react'

interface TenantActionsProps {
  tenantName: string
  onView: () => void
  onEdit: () => void
  onStores: () => void
  onUsers: () => void
}

export function TenantActions({
  tenantName,
  onView,
  onEdit,
  onStores,
  onUsers,
}: TenantActionsProps) {
  const stop = (handler: () => void) => (event: MouseEvent) => {
    event.stopPropagation()
    handler()
  }

  return (
    <div className="row-actions" role="group" aria-label={`Actions for ${tenantName}`}>
      <button
        type="button"
        className="btn btn-sm btn-primary row-actions__primary"
        aria-label={`Open ${tenantName} workspace`}
        onClick={stop(onView)}
      >
        <i className="bi bi-box-arrow-up-right me-1" aria-hidden="true" />
        Open
      </button>
      <span className="row-actions__group">
        <button
          type="button"
          className="btn btn-sm btn-outline-secondary"
          title="Edit"
          aria-label={`Edit ${tenantName}`}
          onClick={stop(onEdit)}
        >
          <i className="bi bi-pencil" aria-hidden="true" />
        </button>
        <button
          type="button"
          className="btn btn-sm btn-outline-secondary"
          title="Stores"
          aria-label={`View stores for ${tenantName}`}
          onClick={stop(onStores)}
        >
          <i className="bi bi-shop" aria-hidden="true" />
        </button>
        <button
          type="button"
          className="btn btn-sm btn-outline-secondary"
          title="Users"
          aria-label={`View users for ${tenantName}`}
          onClick={stop(onUsers)}
        >
          <i className="bi bi-people" aria-hidden="true" />
        </button>
      </span>
    </div>
  )
}
