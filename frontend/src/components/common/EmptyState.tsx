interface EmptyStateAction {
  label: string
  icon?: string
  onClick: () => void
}

interface EmptyStateProps {
  icon: string
  title: string
  description?: string
  action?: EmptyStateAction
}

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="empty-state">
      <div className="empty-state__icon">
        <i className={`bi ${icon}`} aria-hidden="true" />
      </div>
      <h2 className="empty-state__title h5">{title}</h2>
      {description && <p className="empty-state__text">{description}</p>}
      {action && (
        <button type="button" className="btn btn-primary mt-3" onClick={action.onClick}>
          {action.icon && <i className={`bi ${action.icon} me-1`} aria-hidden="true" />}
          {action.label}
        </button>
      )}
    </div>
  )
}
