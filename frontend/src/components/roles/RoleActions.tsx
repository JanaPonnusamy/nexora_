import type { MouseEvent } from 'react'

interface RoleActionsProps {
  roleName: string
  onView: () => void
  onEdit: () => void
  onUsers: () => void
}

export function RoleActions({ roleName, onView, onEdit, onUsers }: RoleActionsProps) {
  const stop = (handler: () => void) => (event: MouseEvent) => {
    event.stopPropagation()
    handler()
  }

  return (
    <div className="row-actions" role="group" aria-label={`Actions for ${roleName}`}>
      <button
        type="button"
        className="btn btn-sm btn-primary row-actions__primary"
        aria-label={`Open ${roleName} workspace`}
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
          aria-label={`Edit ${roleName}`}
          onClick={stop(onEdit)}
        >
          <i className="bi bi-pencil" aria-hidden="true" />
        </button>
        <button
          type="button"
          className="btn btn-sm btn-outline-secondary"
          title="Users"
          aria-label={`View users for ${roleName}`}
          onClick={stop(onUsers)}
        >
          <i className="bi bi-people" aria-hidden="true" />
        </button>
      </span>
    </div>
  )
}
