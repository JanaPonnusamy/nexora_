import { useEffect, useMemo, useState } from 'react'
import { useAsyncData } from '../../hooks/useAsyncData'
import { syncService } from '../../services/syncService'
import { storeService } from '../../services/storeService'
import { EmptyState } from '../common/EmptyState'
import { ErrorState } from '../common/ErrorState'
import { TableSkeleton } from '../common/TableSkeleton'
import { ScheduleFormModal } from './ScheduleFormModal'
import type { Store } from '../../types/store'
import type { SyncSchedule } from '../../types/sync'
import { SxCard, SxCardHead, SxCardBody, SxStat, SxChip, SxButton, SxTable } from './ui'

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
    once: schedules.filter((s) => s.schedule_type === 'ONCE').length,
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
      <div className="row row-cols-2 row-cols-md-4 g-3">
        <div className="col"><SxStat icon="bi-calendar-event" tone="indigo" value={stats.total} label="Total Schedules" /></div>
        <div className="col"><SxStat icon="bi-play-circle" tone="success" value={stats.active} label="Active" /></div>
        <div className="col"><SxStat icon="bi-pause-circle" tone="warning" value={stats.suspended} label="Suspended" /></div>
        <div className="col"><SxStat icon="bi-1-circle" tone="teal" value={stats.once} label="One-time" /></div>
      </div>

      <SxCard>
        <SxCardHead title="Schedules" icon="bi-calendar-event" sub={`${schedules.length} configured`}
          action={
            <div className="d-flex gap-2">
              <SxButton variant="ghost" icon="bi-stars" busy={seeding} onClick={seedDefaults}>Seed defaults</SxButton>
              <SxButton variant="primary" icon="bi-plus-lg" onClick={() => setModal({ kind: 'create' })}>Add Schedule</SxButton>
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
                      <td><SxChip tone={s.schedule_type === 'ONCE' ? 'teal' : 'indigo'}>
                        {s.schedule_type === 'ONCE' ? 'One-time' : 'Daily'}</SxChip></td>
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
