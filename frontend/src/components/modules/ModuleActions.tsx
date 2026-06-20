import type { MouseEvent } from 'react'

interface ModuleActionsProps {
  moduleName: string
  onView: () => void
  onEdit: () => void
}

export function ModuleActions({ moduleName, onView, onEdit }: ModuleActionsProps) {
  const stop = (handler: () => void) => (event: MouseEvent) => {
    event.stopPropagation()
    handler()
  }

  return (
    <div className="row-actions" role="group" aria-label={`Actions for ${moduleName}`}>
      <button
        type="button"
        className="btn btn-sm btn-primary row-actions__primary"
        aria-label={`Open ${moduleName} workspace`}
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
          aria-label={`Edit ${moduleName}`}
          onClick={stop(onEdit)}
        >
          <i className="bi bi-pencil" aria-hidden="true" />
        </button>
      </span>
    </div>
  )
}
