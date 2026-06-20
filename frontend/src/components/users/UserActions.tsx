import type { MouseEvent } from 'react'

interface UserActionsProps {
  userName: string
  onView: () => void
  onEdit: () => void
  onRoles: () => void
  onStores: () => void
}

export function UserActions({ userName, onView, onEdit, onRoles, onStores }: UserActionsProps) {
  const stop = (handler: () => void) => (event: MouseEvent) => {
    event.stopPropagation()
    handler()
  }

  return (
    <div className="row-actions" role="group" aria-label={`Actions for ${userName}`}>
      <button
        type="button"
        className="btn btn-sm btn-primary row-actions__primary"
        aria-label={`Open ${userName} workspace`}
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
          aria-label={`Edit ${userName}`}
          onClick={stop(onEdit)}
        >
          <i className="bi bi-pencil" aria-hidden="true" />
        </button>
        <button
          type="button"
          className="btn btn-sm btn-outline-secondary"
          title="Roles"
          aria-label={`View roles for ${userName}`}
          onClick={stop(onRoles)}
        >
          <i className="bi bi-person-badge" aria-hidden="true" />
        </button>
        <button
          type="button"
          className="btn btn-sm btn-outline-secondary"
          title="Store access"
          aria-label={`View store access for ${userName}`}
          onClick={stop(onStores)}
        >
          <i className="bi bi-shop" aria-hidden="true" />
        </button>
      </span>
    </div>
  )
}
