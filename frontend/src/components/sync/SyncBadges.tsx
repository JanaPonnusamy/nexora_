const CONNECTION_ICONS: Record<string, string> = {
  LAN: 'bi-ethernet',
  WiFi: 'bi-wifi',
  Internet: 'bi-globe2',
  Offline: 'bi-plug',
}

export function ConnectionType({ value }: { value: string }) {
  const icon = CONNECTION_ICONS[value] ?? 'bi-question-circle'
  return (
    <span className="d-inline-flex align-items-center gap-1">
      <i className={`bi ${icon}`} aria-hidden="true" />
      {value}
    </span>
  )
}

export function AgentBadge({ status }: { status: string }) {
  const online = status === 'Online'
  return (
    <span className={`badge ${online ? 'text-bg-success' : 'text-bg-secondary'}`}>{status}</span>
  )
}

const STATUS_TONE: Record<string, string> = {
  COMPLETED: 'text-bg-success',
  FAILED: 'text-bg-danger',
  RUNNING: 'text-bg-primary',
  Syncing: 'text-bg-primary',
  QUEUED: 'text-bg-warning',
  Online: 'text-bg-success',
  Offline: 'text-bg-secondary',
}

export function SyncStatusBadge({ status }: { status: string | null }) {
  if (!status) return <span className="text-secondary">—</span>
  return <span className={`badge ${STATUS_TONE[status] ?? 'text-bg-secondary'}`}>{status}</span>
}
