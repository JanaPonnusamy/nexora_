import { useState } from 'react'
import type { FormEvent } from 'react'
import type { ScheduleInput, SyncSchedule } from '../../types/sync'
import type { Store } from '../../types/store'
import { syncService } from '../../services/syncService'

interface Props {
  mode: 'create' | 'edit'
  schedule?: SyncSchedule
  stores: Store[]
  onClose: () => void
  onSaved: () => void
}

function initialTime(schedule?: SyncSchedule): string {
  // DAILY start_time is "2000-01-01THH:MM:SS" -> take HH:MM.
  if (schedule?.schedule_type === 'DAILY' && schedule.start_time) {
    return schedule.start_time.slice(11, 16)
  }
  return '06:15'
}

function initialDateTime(schedule?: SyncSchedule): string {
  if (schedule?.schedule_type === 'ONCE' && schedule.start_time) {
    return schedule.start_time.slice(0, 16)
  }
  const d = new Date(Date.now() + 60 * 60 * 1000)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export function ScheduleFormModal({ mode, schedule, stores, onClose, onSaved }: Props) {
  const [name, setName] = useState(schedule?.schedule_name ?? '')
  const [type, setType] = useState(schedule?.schedule_type ?? 'DAILY')
  const [storeId, setStoreId] = useState(schedule?.store_id ?? '')
  const [time, setTime] = useState(initialTime(schedule))
  const [dateTime, setDateTime] = useState(initialDateTime(schedule))
  const [syncMode, setSyncMode] = useState(schedule?.sync_mode ?? 'FULL')
  const [enabled, setEnabled] = useState(schedule?.is_enabled ?? true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!name.trim()) {
      setError('Schedule name is required')
      return
    }
    const startTime = type === 'DAILY' ? `2000-01-01T${time}:00` : `${dateTime}:00`
    const input: ScheduleInput = {
      schedule_name: name.trim(),
      schedule_type: type,
      store_id: storeId || null,
      start_time: startTime,
      sync_mode: syncMode,
      is_enabled: enabled,
    }
    setSubmitting(true)
    setError(null)
    try {
      if (mode === 'create') await syncService.createSchedule(input)
      else if (schedule) await syncService.updateSchedule(schedule.schedule_id, input)
      onSaved()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save schedule')
      setSubmitting(false)
    }
  }

  return (
    <>
      <div className="modal fade show d-block" tabIndex={-1} role="dialog">
        <div className="modal-dialog modal-dialog-centered">
          <div className="modal-content">
            <form onSubmit={handleSubmit}>
              <div className="modal-header">
                <h5 className="modal-title">{mode === 'create' ? 'Add Schedule' : 'Edit Schedule'}</h5>
                <button type="button" className="btn-close" aria-label="Close" onClick={onClose} disabled={submitting} />
              </div>
              <div className="modal-body vstack gap-3">
                {error && <div className="alert alert-danger py-2 mb-0">{error}</div>}

                <div>
                  <label htmlFor="sch-name" className="form-label">Schedule Name</label>
                  <input id="sch-name" className="form-control" value={name}
                    onChange={(e) => setName(e.target.value)} placeholder="e.g. NMA Morning Sync" />
                </div>

                <div className="row g-3">
                  <div className="col-md-6">
                    <label htmlFor="sch-type" className="form-label">Type</label>
                    <select id="sch-type" className="form-select" value={type} onChange={(e) => setType(e.target.value)}>
                      <option value="DAILY">Daily (recurring)</option>
                      <option value="ONCE">One-time</option>
                    </select>
                  </div>
                  <div className="col-md-6">
                    {type === 'DAILY' ? (
                      <>
                        <label htmlFor="sch-time" className="form-label">Run At (daily)</label>
                        <input id="sch-time" type="time" className="form-control" value={time}
                          onChange={(e) => setTime(e.target.value)} />
                      </>
                    ) : (
                      <>
                        <label htmlFor="sch-dt" className="form-label">Run At (one-time)</label>
                        <input id="sch-dt" type="datetime-local" className="form-control" value={dateTime}
                          onChange={(e) => setDateTime(e.target.value)} />
                      </>
                    )}
                  </div>
                  <div className="col-md-6">
                    <label htmlFor="sch-store" className="form-label">Store</label>
                    <select id="sch-store" className="form-select" value={storeId} onChange={(e) => setStoreId(e.target.value)}>
                      <option value="">All stores</option>
                      {stores.map((s) => (
                        <option key={s.store_id} value={s.store_id}>{s.store_code} — {s.store_name}</option>
                      ))}
                    </select>
                  </div>
                  <div className="col-md-6">
                    <label htmlFor="sch-mode" className="form-label">Sync Mode</label>
                    <select id="sch-mode" className="form-select" value={syncMode} onChange={(e) => setSyncMode(e.target.value)}>
                      <option value="FULL">Full</option>
                      <option value="UPSERT">Upsert</option>
                      <option value="ROLLING_WINDOW">Rolling Window</option>
                    </select>
                  </div>
                </div>

                <div className="form-check form-switch">
                  <input className="form-check-input" type="checkbox" role="switch" id="sch-enabled"
                    checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
                  <label className="form-check-label" htmlFor="sch-enabled">Enabled</label>
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-link" onClick={onClose} disabled={submitting}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={submitting}>
                  {submitting ? <><span className="spinner-border spinner-border-sm me-2" aria-hidden="true" />Saving…</> : 'Save'}
                </button>
              </div>
            </form>
          </div>
        </div>
      </div>
      <div className="modal-backdrop fade show" />
    </>
  )
}
