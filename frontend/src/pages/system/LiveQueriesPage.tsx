import { useCallback, useEffect, useRef, useState } from 'react'
import { dbMonitorService } from '../../services/dbMonitorService'
import { ApiError } from '../../services/apiClient'
import { useAuth } from '../../hooks/useAuth'
import { isSuperAdmin } from '../label-export/labelExportAccess'
import type { DbMonitorRequest, DbMonitorSession } from '../../types/legacyOrder'
import './live-queries.css'

const POLL_MS = 5000

function errorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.message
  if (err instanceof Error) return err.message
  return fallback
}

function fmtMs(ms: number | null | undefined): string {
  if (ms == null) return '—'
  if (ms < 1000) return `${ms} ms`
  const s = ms / 1000
  if (s < 60) return `${s.toFixed(1)} s`
  const m = Math.floor(s / 60)
  return `${m}m ${Math.round(s - m * 60)}s`
}

export default function LiveQueriesPage() {
  const { user } = useAuth()
  const admin = isSuperAdmin(user)

  const [requests, setRequests] = useState<DbMonitorRequest[]>([])
  const [showAllSessions, setShowAllSessions] = useState(false)
  const [sessions, setSessions] = useState<DbMonitorSession[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [killing, setKilling] = useState<number | null>(null)
  const [note, setNote] = useState('')
  const [confirmKill, setConfirmKill] = useState<number | null>(null)
  const [auto, setAuto] = useState(true)
  const mounted = useRef(true)

  useEffect(
    () => () => {
      mounted.current = false
    },
    [],
  )

  const load = useCallback(() => {
    if (!admin) return
    setLoading(true)
    setError('')
    const calls: [Promise<{ requests: DbMonitorRequest[] }>, Promise<{ sessions: DbMonitorSession[] }> | null] = [
      dbMonitorService.activeRequests(),
      showAllSessions ? dbMonitorService.allSessions() : null,
    ]
    Promise.all([calls[0], calls[1] ?? Promise.resolve(null)])
      .then(([reqs, sess]) => {
        if (!mounted.current) return
        setRequests(reqs.requests || [])
        if (sess) setSessions(sess.sessions || [])
      })
      .catch((err: unknown) => {
        if (mounted.current) setError(errorMessage(err, 'Could not load live queries.'))
      })
      .finally(() => {
        if (mounted.current) setLoading(false)
      })
  }, [admin, showAllSessions])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    if (!auto || !admin) return undefined
    const t = setInterval(load, POLL_MS)
    return () => clearInterval(t)
  }, [auto, admin, load])

  const kill = async (sessionId: number) => {
    setKilling(sessionId)
    setError('')
    setNote('')
    try {
      await dbMonitorService.killSession(sessionId)
      setNote(`Session ${sessionId} killed.`)
      setConfirmKill(null)
      await load()
    } catch (err) {
      setError(errorMessage(err, `Could not kill session ${sessionId}.`))
    } finally {
      setKilling(null)
    }
  }

  if (!admin) {
    return (
      <section className="live-queries">
        <div className="status-line error">Live Queries is restricted to platform admins.</div>
      </section>
    )
  }

  return (
    <section className="live-queries">
      <header className="lq-head">
        <div>
          <h2>Live Queries · Repair</h2>
          <p>What&apos;s running right now on central OrderNMC, longest-running first. Kill a stuck session to release its locks.</p>
        </div>
        <div className="lq-tools">
          <label className="lq-checkbox">
            <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} />
            Auto-refresh
          </label>
          <button type="button" className="secondary-button" onClick={load} disabled={loading}>
            {loading ? 'Loading…' : 'Refresh'}
          </button>
        </div>
      </header>

      {error && <div className="status-line error">{error}</div>}
      {note && <div className="status-line lq-ok">{note}</div>}

      <section className="lq-card">
        <header className="lq-card-head">
          <h3>Active requests</h3>
          <span className="lq-muted">{requests.length} running</span>
        </header>
        <div className="lq-tablewrap">
          <table className="lq-table">
            <thead>
              <tr>
                <th>SPID</th>
                <th>Elapsed</th>
                <th>Status</th>
                <th>Wait</th>
                <th>Blocked by</th>
                <th>CPU</th>
                <th>Reads</th>
                <th>Rows</th>
                <th className="lq-left">Login / Host</th>
                <th className="lq-left">Query</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {requests.map((r) => (
                <tr key={r.session_id} className={r.blocking_session_id ? 'lq-warn-row' : ''}>
                  <td>{r.session_id}</td>
                  <td>{fmtMs(r.total_elapsed_ms)}</td>
                  <td>{r.status}</td>
                  <td>{r.wait_type || '—'}</td>
                  <td>{r.blocking_session_id || '—'}</td>
                  <td>{fmtMs(r.cpu_time_ms)}</td>
                  <td>{r.logical_reads != null ? r.logical_reads.toLocaleString() : '—'}</td>
                  <td>{r.row_count != null ? r.row_count.toLocaleString() : '—'}</td>
                  <td className="lq-left">
                    {r.login_name} @ {r.host_name || '—'}
                    <br />
                    <span className="lq-muted">{r.program_name}</span>
                  </td>
                  <td className="lq-left lq-query-cell" title={r.query_text || ''}>
                    {r.query_text ? r.query_text.slice(0, 160) : '—'}
                  </td>
                  <td>
                    {confirmKill === r.session_id ? (
                      <>
                        <button
                          type="button"
                          className="danger-button"
                          disabled={killing === r.session_id}
                          onClick={() => kill(r.session_id)}
                        >
                          {killing === r.session_id ? 'Killing…' : 'Confirm kill'}
                        </button>
                        <button type="button" className="secondary-button" onClick={() => setConfirmKill(null)}>
                          Cancel
                        </button>
                      </>
                    ) : (
                      <button type="button" className="danger-button" onClick={() => setConfirmKill(r.session_id)}>
                        Kill
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {!loading && !requests.length && (
                <tr>
                  <td colSpan={11} className="lq-muted">
                    Nothing is actively running right now.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="lq-card">
        <header className="lq-card-head">
          <h3>All sessions</h3>
          <div className="lq-tools">
            <label className="lq-checkbox">
              <input type="checkbox" checked={showAllSessions} onChange={(e) => setShowAllSessions(e.target.checked)} />
              Show (includes idle connections)
            </label>
          </div>
        </header>
        {showAllSessions && (
          <div className="lq-tablewrap">
            <table className="lq-table">
              <thead>
                <tr>
                  <th>SPID</th>
                  <th>Status</th>
                  <th>Last request</th>
                  <th>Elapsed</th>
                  <th>Blocked by</th>
                  <th className="lq-left">Login / Host / Program</th>
                </tr>
              </thead>
              <tbody>
                {sessions.map((s) => (
                  <tr key={s.session_id}>
                    <td>{s.session_id}</td>
                    <td>{s.status}</td>
                    <td>{s.last_request_start_time ? new Date(s.last_request_start_time).toLocaleTimeString() : '—'}</td>
                    <td>{fmtMs(s.total_elapsed_ms)}</td>
                    <td>{s.blocking_session_id || '—'}</td>
                    <td className="lq-left">
                      {s.login_name} @ {s.host_name || '—'} · {s.program_name}
                    </td>
                  </tr>
                ))}
                {!sessions.length && (
                  <tr>
                    <td colSpan={6} className="lq-muted">
                      No sessions.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </section>
  )
}
