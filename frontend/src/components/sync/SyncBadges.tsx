import { SxChip } from './ui'
import type { Tone } from './ui'

const CONNECTION_ICONS: Record<string, string> = {
  LAN: 'bi-ethernet',
  WiFi: 'bi-wifi',
  Internet: 'bi-globe2',
  Offline: 'bi-plug',
}

export function ConnectionType({ value }: { value: string }) {
  const icon = CONNECTION_ICONS[value] ?? 'bi-question-circle'
  return (
    <span className="sx-conn">
      <i className={`bi ${icon}`} aria-hidden="true" />
      {value}
    </span>
  )
}

export function AgentBadge({ status }: { status: string }) {
  const online = status === 'Online'
  return (
    <SxChip tone={online ? 'success' : 'muted'} dot running={online}>
      {status}
    </SxChip>
  )
}

const STATUS_TONE: Record<string, Tone> = {
  COMPLETED: 'success',
  FAILED: 'danger',
  RUNNING: 'indigo',
  Syncing: 'indigo',
  QUEUED: 'warning',
  PENDING: 'warning',
  PAUSED: 'info',
  CANCELLED: 'muted',
  PARTIAL: 'warning',
  PARTIAL_SUCCESS: 'warning',
  Online: 'success',
  Offline: 'muted',
}

const STATUS_LABEL: Record<string, string> = {
  Syncing: 'Syncing',
  PARTIAL: 'Partial Success',
  PARTIAL_SUCCESS: 'Partial Success',
}

export function SyncStatusBadge({ status, compact = false }: { status: string | null; compact?: boolean }) {
  if (!status) return <span className="sx-dim">-</span>
  const tone = STATUS_TONE[status] ?? 'muted'
  const running = status === 'Syncing' || status === 'RUNNING'
  return (
    <SxChip tone={tone} dot running={running} compact={compact}>
      {STATUS_LABEL[status] ?? status}
    </SxChip>
  )
}

export function SyncTypeBadge({ value }: { value: string | null }) {
  if (!value) return <span className="sx-dim">-</span>
  const v = value.toUpperCase()
  if (v.includes('ROLL')) return <SxChip tone="violet">Rolling Window</SxChip>
  return <SxChip tone="teal">Upsert</SxChip>
}
