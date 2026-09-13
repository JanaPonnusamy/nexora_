import { useEffect, useMemo, useState } from 'react'
import { useAsyncData } from '../../hooks/useAsyncData'
import { syncService } from '../../services/syncService'
import { storeService } from '../../services/storeService'
import { EmptyState } from '../common/EmptyState'
import { ErrorState } from '../common/ErrorState'
import { TableSkeleton } from '../common/TableSkeleton'
import { ScheduleFormModal } from './ScheduleFormModal'
import type { Store } from '../../types/store'
import type { ScheduleBoardRow, SyncSchedule } from '../../types/sync'
import { SxCard, SxCardHead, SxCardBody, SxStat, SxChip, SxButton, SxTable } from './ui'

const BOARD_REFRESH_MS = 15_000

function fmtDuration(seconds: number | null): string {
  if (seconds == null) return '—'
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return m > 0 ? `${m}m ${s}s` : `${s}s`
}

function cadenceLabel(row: ScheduleBoardRow): string {
  if (!row.schedule_name) return 'No schedule'
  if (row.schedule_type === 'INTERVAL' && row.interval_minutes) return `Every ${row.interval_minutes} min`
  if (row.schedule_type === 'DAILY') return 'Daily'
  if (row.schedule_type === 'ONCE') return 'One-time'
  return row.schedule_name
}

function statusChipTone(status: string | null): 'success' | 'danger' | 'warning' | 'muted' {
  if (status === 'COMPLETED') return 'success'
  if (status === 'FAILED') return 'danger'
  if (status === 'SKIPPED' || status === 'QUEUED') return 'warning'
  return 'muted'
}

function ScheduleBoardPanel() {
  const [rows, setRows] = useState<ScheduleBoardRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const data = await syncService.scheduleBoard()
        if (!cancelled) { setRows(data); setError(null) }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load store status')
      }
    }
    void load()
    const timer = window.setInterval(load, BOARD_REFRESH_MS)
    return () => { cancelled = true; window.clearInterval(timer) }
  }, [])

  return (
    <SxCard className="sx-pane">
      <SxCardHead title="Store Status" icon="bi-hdd-network"
        sub={rows ? `${rows.length} store${rows.length === 1 ? '' : 's'} · refreshes every ${BOARD_REFRESH_MS / 1000}s` : undefined} />
      <SxCardBody flush>
        {error && <div className="sx-alert sx-alert--danger">{error}</div>}
        {!rows && !error && <TableSkeleton rows={4} columns={7} />}
        {rows && rows.length === 0 && (
          <EmptyState icon="bi-hdd-network" title="No active stores" description="No stores are currently active." />
        )}
        {rows && rows.length > 0 && (
          <SxTable>
            <thead>
              <tr>
                <th>Store</th><th>Schedule</th><th>Next Run</th><th>Last Run</th>
                <th>Last Status</th><th>Currently Running</th><th className="sx-num">Last Duration</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.store_id}>
                  <td className="sx-strong">{r.store_code}</td>
                  <td className="sx-dim">{cadenceLabel(r)}</td>
                  <td>{r.next_run_at ? new Date(r.next_run_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'}</td>
                  <td>{r.last_run_at ? new Date(r.last_run_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'}</td>
                  <td>{r.last_status ? <SxChip tone={statusChipTone(r.last_status)}>{r.last_status}</SxChip> : '—'}</td>
                  <td>{r.is_running
                    ? <SxChip tone="info" dot running>Syncing</SxChip>
                    : <span className="sx-dim">Idle</span>}</td>
                  <td className="sx-num">{fmtDuration(r.last_duration_seconds)}</td>
                </tr>
              ))}
            </tbody>
          </SxTable>
        )}
      </SxCardBody>
    </SxCard>
  )
}

type Modal =
  | { kind: 'create' }
  | { kind: 'edit'; schedule: SyncSchedule }
  | { kind: 'suspend'; schedule: SyncSchedule }
  | null

function statusTone(status: string): 'success' | 'warning' | 'muted' {
  if (status === 'Active') return 'success'
  if (status === 'Suspended') return 'warning'
  return 'muted'
}

function runAtLabel(s: SyncSchedule): string {
  if (s.schedule_type === 'INTERVAL') return `Every ${s.interval_minutes ?? '?'} min`
  if (!s.start_time) return '—'
  if (s.schedule_type === 'DAILY') {
    const hm = s.start_time.slice(11, 16)
    return `${hm} daily`
  }
  return new Date(s.start_time).toLocaleString([], {
    dateStyle: 'medium', timeStyle: 'short',
  })
}

function fmtDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })
}

async function fetchAll() {
  const [schedules, stores] = await Promise.all([
    syncService.schedules(),
    storeService.list(),
  ])
  return { schedules, stores }
}

export function SchedulesTab() {
  const { data, isLoading, error, reload } = useAsyncData(fetchAll)
  const [modal, setModal] = useState<Modal>(null)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [seeding, setSeeding] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  const schedules = useMemo(() => data?.schedules ?? [], [data])
  const stores: Store[] = useMemo(() => data?.stores ?? [], [data])

  const stats = useMemo(() => ({
    total: schedules.length,
    active: schedules.filter((s) => s.status === 'Active').length,
    suspended: schedules.filter((s) => s.status === 'Suspended').length,
    interval: schedules.filter((s) => s.schedule_type === 'INTERVAL').length,
  }), [schedules])

  const run = async (id: number, fn: () => Promise<unknown>) => {
    setBusyId(id)
    setActionError(null)
    try {
      await fn()
      await reload()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Action failed')
    } finally {
      setBusyId(null)
    }
  }

  const toggleEnabled = (s: SyncSchedule) =>
    run(s.schedule_id, () => syncService.setScheduleStatus(s.schedule_id, !s.is_enabled))

  const removeSchedule = (s: SyncSchedule) => {
    if (!window.confirm(`Delete schedule "${s.schedule_name}"?`)) return
    void run(s.schedule_id, () => syncService.deleteSchedule(s.schedule_id))
  }

  const clearSuspend = (s: SyncSchedule) =>
    run(s.schedule_id, () => syncService.suspendSchedule(s.schedule_id, null))

  const seedDefaults = async () => {
    setSeeding(true)
    setActionError(null)
    setNotice(null)
    try {
      const res = await syncService.seedSchedules()
      setNotice(res.created > 0
        ? `Seeded ${res.created} default schedule(s) across ${res.stores} stores.`
        : `Defaults already present (${res.stores} stores).`)
      await reload()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Seeding failed')
    } finally {
      setSeeding(false)
    }
  }

  if (isLoading) return <TableSkeleton rows={6} columns={6} />
  if (error || !data) return <ErrorState description={error ?? 'Failed to load schedules'} onRetry={reload} />

  return (
    <div className="sx-stack">
      <div className="row row-cols-2 row-cols-md-4 g-2">
        <div className="col"><SxStat icon="bi-calendar-event" tone="indigo" value={stats.total} label="Total Schedules" /></div>
        <div className="col"><SxStat icon="bi-play-circle" tone="success" value={stats.active} label="Active" /></div>
        <div className="col"><SxStat icon="bi-pause-circle" tone="warning" value={stats.suspended} label="Suspended" /></div>
        <div className="col"><SxStat icon="bi-arrow-repeat" tone="teal" value={stats.interval} label="Every N Minutes" /></div>
      </div>

      <ScheduleBoardPanel />

      <SxCard className="sx-pane">
        <SxCardHead title="Schedules" icon="bi-calendar-event" sub={`${schedules.length} configured`}
          action={
            <div className="d-flex gap-2">
              <SxButton sm variant="ghost" icon="bi-stars" busy={seeding} onClick={seedDefaults}>Seed</SxButton>
              <SxButton sm variant="primary" icon="bi-plus-lg" onClick={() => setModal({ kind: 'create' })}>Add</SxButton>
            </div>
          } />
        <SxCardBody>
          {notice && <div className="sx-alert sx-alert--info">{notice}</div>}
          {actionError && <div className="sx-alert sx-alert--danger">{actionError}</div>}
          {schedules.length === 0 && (
            <EmptyState icon="bi-calendar-event" title="No schedules yet"
              description="Add a schedule, or seed per-store daily defaults."
              action={{ label: 'Seed defaults', icon: 'bi-stars', onClick: seedDefaults }} />
          )}
        </SxCardBody>

        {schedules.length > 0 && (
          <SxCardBody flush>
            <SxTable>
              <thead>
                <tr>
                  <th>Schedule</th><th>Type</th><th>Run At</th><th>Store</th>
                  <th>Mode</th><th>Status</th><th>Suspended Until</th><th className="sx-num">Actions</th>
                </tr>
              </thead>
              <tbody>
                {schedules.map((s) => {
                  const busy = busyId === s.schedule_id
                  return (
                    <tr key={s.schedule_id}>
                      <td className="sx-strong">{s.schedule_name}</td>
                      <td><SxChip tone={s.schedule_type === 'ONCE' ? 'teal' : s.schedule_type === 'INTERVAL' ? 'success' : 'indigo'}>
                        {s.schedule_type === 'ONCE' ? 'One-time' : s.schedule_type === 'INTERVAL' ? 'Interval' : 'Daily'}</SxChip></td>
                      <td>{runAtLabel(s)}</td>
                      <td>{s.store_code ? <span className="sx-strong">{s.store_code}</span> : <span className="sx-dim">All stores</span>}</td>
                      <td className="sx-dim">{s.sync_mode}</td>
                      <td><SxChip tone={statusTone(s.status)} dot running={s.status === 'Active'}>{s.status}</SxChip></td>
                      <td className="sx-dim" style={{ fontSize: '0.82rem' }}>
                        {s.suspended_until ? (
                          <span className="d-inline-flex align-items-center gap-1">
                            {fmtDate(s.suspended_until)}
                            <button type="button" className="sx-linkbtn" title="Clear suspension"
                              onClick={() => clearSuspend(s)} disabled={busy}>×</button>
                          </span>
                        ) : '—'}
                      </td>
                      <td className="sx-num">
                        <div className="d-inline-flex gap-1">
                          <SxButton variant="ghost" sm icon={s.is_enabled ? 'bi-toggle-on' : 'bi-toggle-off'}
                            title={s.is_enabled ? 'Disable' : 'Enable'} busy={busy} onClick={() => toggleEnabled(s)} />
                          <SxButton variant="ghost" sm icon="bi-pause-circle" title="Suspend until…"
                            disabled={busy} onClick={() => setModal({ kind: 'suspend', schedule: s })} />
                          <SxButton variant="ghost" sm icon="bi-pencil" title="Edit"
                            disabled={busy} onClick={() => setModal({ kind: 'edit', schedule: s })} />
                          <SxButton variant="danger" sm icon="bi-trash" title="Delete"
                            busy={busy} onClick={() => removeSchedule(s)} />
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </SxTable>
          </SxCardBody>
        )}
      </SxCard>

      {(modal?.kind === 'create' || modal?.kind === 'edit') && (
        <ScheduleFormModal
          mode={modal.kind}
          schedule={modal.kind === 'edit' ? modal.schedule : undefined}
          stores={stores}
          onClose={() => setModal(null)}
          onSaved={() => { setModal(null); void reload() }}
        />
      )}
      {modal?.kind === 'suspend' && (
        <SuspendModal
          schedule={modal.schedule}
          onClose={() => setModal(null)}
          onSaved={() => { setModal(null); void reload() }}
        />
      )}
    </div>
  )
}

function SuspendModal({ schedule, onClose, onSaved }: {
  schedule: SyncSchedule; onClose: () => void; onSaved: () => void
}) {
  const [until, setUntil] = useState(() => {
    const d = new Date(Date.now() + 24 * 60 * 60 * 1000)
    const pad = (n: number) => String(n).padStart(2, '0')
    return schedule.suspended_until?.slice(0, 16)
      ?? `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
  })
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async () => {
    setSubmitting(true)
    setError(null)
    try {
      await syncService.suspendSchedule(schedule.schedule_id, `${until}:00`)
      onSaved()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to suspend')
      setSubmitting(false)
    }
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <>
      <div className="modal fade show d-block" tabIndex={-1} role="dialog">
        <div className="modal-dialog modal-dialog-centered modal-sm">
          <div className="modal-content">
            <div className="modal-header">
              <h5 className="modal-title">Suspend until</h5>
              <button type="button" className="btn-close" aria-label="Close" onClick={onClose} disabled={submitting} />
            </div>
            <div className="modal-body vstack gap-2">
              {error && <div className="alert alert-danger py-2 mb-0">{error}</div>}
              <div className="text-secondary small">“{schedule.schedule_name}” will not run until:</div>
              <input type="datetime-local" className="form-control" value={until}
                onChange={(e) => setUntil(e.target.value)} />
            </div>
            <div className="modal-footer">
              <button type="button" className="btn btn-link" onClick={onClose} disabled={submitting}>Cancel</button>
              <button type="button" className="btn btn-warning" onClick={submit} disabled={submitting}>
                {submitting ? 'Saving…' : 'Suspend'}
              </button>
            </div>
          </div>
        </div>
      </div>
      <div className="modal-backdrop fade show" />
    </>
  )
}
