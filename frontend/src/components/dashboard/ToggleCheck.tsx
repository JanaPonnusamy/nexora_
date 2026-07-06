interface ToggleCheckProps {
  checked: boolean
  onClick: () => void
  label: string
  busy?: boolean
}

/** Compact check toggle — replaces oversized bordered checkbox buttons. */
export function ToggleCheck({ checked, onClick, label, busy }: ToggleCheckProps) {
  return (
    <button
      type="button"
      className={`toggle-check${checked ? ' toggle-check--on' : ''}`}
      aria-pressed={checked}
      aria-label={label}
      disabled={busy}
      onClick={onClick}
    >
      {busy ? (
        <span className="spinner-border spinner-border-sm" aria-hidden="true" />
      ) : (
        <i className={`bi ${checked ? 'bi-check-lg' : 'bi-dash'}`} aria-hidden="true" />
      )}
    </button>
  )
}
