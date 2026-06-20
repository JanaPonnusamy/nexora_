interface StatusBadgeProps {
  active: boolean
}

export function StatusBadge({ active }: StatusBadgeProps) {
  return (
    <span className={`badge status-badge ${active ? 'status-badge--active' : 'status-badge--inactive'}`}>
      <i className="bi bi-circle-fill" aria-hidden="true" />
      {active ? 'Active' : 'Inactive'}
    </span>
  )
}
