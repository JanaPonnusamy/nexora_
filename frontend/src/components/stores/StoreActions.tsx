import type { MouseEvent } from 'react'

interface StoreActionsProps {
  storeName: string
  onView: () => void
  onEdit: () => void
  onUsers: () => void
  onRoles: () => void
}

export function StoreActions({
  storeName,
  onView,
  onEdit,
  onUsers,
  onRoles,
}: StoreActionsProps) {
  const stop = (handler: () => void) => (event: MouseEvent) => {
    event.stopPropagation()
    handler()
  }

  return (
    <div className="row-actions" role="group" aria-label={`Actions for ${storeName}`}>
      <button
        type="button"
        className="btn btn-sm btn-primary row-actions__primary"
        aria-label={`Open ${storeName} workspace`}
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
          aria-label={`Edit ${storeName}`}
          onClick={stop(onEdit)}
        >
          <i className="bi bi-pencil" aria-hidden="true" />
        </button>
        <button
          type="button"
          className="btn btn-sm btn-outline-secondary"
          title="Users"
          aria-label={`View users for ${storeName}`}
          onClick={stop(onUsers)}
        >
          <i className="bi bi-people" aria-hidden="true" />
        </button>
        <button
          type="button"
          className="btn btn-sm btn-outline-secondary"
          title="Roles"
          aria-label={`View roles for ${storeName}`}
          onClick={stop(onRoles)}
        >
          <i className="bi bi-person-badge" aria-hidden="true" />
        </button>
      </span>
    </div>
  )
}
