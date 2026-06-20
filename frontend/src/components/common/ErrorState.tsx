interface ErrorStateProps {
  title?: string
  description?: string
  onRetry?: () => void
}

export function ErrorState({
  title = 'Something went wrong',
  description,
  onRetry,
}: ErrorStateProps) {
  return (
    <div className="empty-state">
      <div className="empty-state__icon empty-state__icon--danger">
        <i className="bi bi-exclamation-triangle" aria-hidden="true" />
      </div>
      <h2 className="empty-state__title h5">{title}</h2>
      {description && <p className="empty-state__text">{description}</p>}
      {onRetry && (
        <button type="button" className="btn btn-outline-secondary btn-sm mt-3" onClick={onRetry}>
          <i className="bi bi-arrow-clockwise me-1" aria-hidden="true" />
          Try again
        </button>
      )}
    </div>
  )
}
