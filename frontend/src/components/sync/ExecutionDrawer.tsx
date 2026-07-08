import { useEffect, useMemo, useState } from 'react'
import { syncService } from '../../services/syncService'
import { formatDateTime } from '../../utils/format'
import { SyncStatusBadge, SyncTypeBadge } from './SyncBadges'
import { SxChip, SxTable } from './ui'
import type {
  ExecutionChunkRow,
  ExecutionErrorRow,
  ExecutionSummary,
  ExecutionTableRow,
  SyncHistoryRow,
} from '../../types/sync'

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return '—'
  if (seconds < 60) return `${seconds}s`
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  if (m < 60) return `${m}m ${s}s`
  const h = Math.floor(m / 60)
  return `${h}h ${m % 60}m`
}

function num(n: number | null | undefined): string {
  return (n ?? 0).toLocaleString()
}

/* A single labelled value in the summary grid. */
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="sx-field">
      <div className="sx-field__label">{label}</div>
      <div className="sx-field__value">{children}</div>
    </div>
  )
}

/* ---- Table row (expandable to its chunks) -------------------------------- */

function TableRow({ execId, row }: { execId: string; row: ExecutionTableRow }) {
  const [open, setOpen] = useState(false)
  const [chunks, setChunks] = useState<ExecutionChunkRow[] | null>(null)
  const [loading, setLoading] = useState(false)

  const toggle = async () => {
    const next = !open
    setOpen(next)
    if (next && chunks === null) {
      setLoading(true)
      try {
        setChunks(await syncService.executionChunks(execId, row.table_name))
      } finally {
        setLoading(false)
      }
    }
  }

  return (
    <>
      <tr className="sx-exrow" onClick={toggle}>
        <td className="sx-dim">
          <i className={`bi ${open ? 'bi-chevron-down' : 'bi-chevron-right'} me-1`} aria-hidden="true" />
          {row.order}
        </td>
        <td className="sx-strong">{row.table_name}</td>
        <td className="sx-dim">{row.direction}</td>
        <td className="sx-num">{num(row.rows_read)}</td>
        <td className="sx-num">{num(row.rows_uploaded)}</td>
        <td className="sx-num">{num(row.rows_inserted)}</td>
        <td className="sx-num">{num(row.rows_updated)}</td>
        <td className="sx-num">{num(row.rows_skipped)}</td>
        <td>{formatDuration(row.duration_seconds)}</td>
        <td><SyncStatusBadge status={row.status} /></td>
      </tr>
      {open && (
        <tr className="sx-exrow__panel">
          <td colSpan={10}>
            {loading ? (
              <div className="sx-inline-load">Loading chunks…</div>
            ) : chunks && chunks.length > 0 ? (
              <table className="sx-subtable">
                <thead>
                  <tr>
                    <th>Chunk</th><th className="sx-num">Rows</th>
                    <th>Start</th><th>End</th><th>Duration</th>
                    <th className="sx-num">Retries</th><th>Result</th>
                  </tr>
                </thead>
                <tbody>
                  {chunks.map((c) => (
                    <tr key={c.chunk_execution_id}>
                      <td className="sx-strong">#{c.chunk_no}</td>
                      <td className="sx-num">{num(c.rows)}</td>
                      <td className="sx-dim">{formatDateTime(c.started_at)}</td>
                      <td className="sx-dim">{formatDateTime(c.completed_at)}</td>
                      <td>{c.duration_ms != null ? `${c.duration_ms} ms` : '—'}</td>
                      <td className="sx-num">{c.retry_count}</td>
                      <td><SyncStatusBadge status={c.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="sx-inline-load sx-dim">
                No per-chunk records were retained for this table.
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  )
}

/* ---- Timeline ------------------------------------------------------------ */

function Timeline({ summary }: { summary: ExecutionSummary }) {
  const stages = summary.timeline
  return (
    <ol className="sx-timeline">
      {stages.map((stage, i) => {
        const prev = i > 0 ? stages[i - 1].at : null
        let delta: number | null = null
        if (prev && stage.at) {
          delta = Math.round((new Date(stage.at).getTime() - new Date(prev).getTime()) / 1000)
        }
        const done = stage.at != null
        return (
          <li key={stage.stage} className={`sx-timeline__item${done ? '' : ' sx-timeline__item--pending'}`}>
            <span className="sx-timeline__dot" />
            <div className="sx-timeline__body">
              <div className="sx-timeline__stage">{stage.stage}</div>
              <div className="sx-timeline__at">{formatDateTime(stage.at)}</div>
            </div>
            {delta != null && delta >= 0 && (
              <span className="sx-timeline__delta">+{formatDuration(delta)}</span>
            )}
          </li>
        )
      })}
    </ol>
  )
}

/* ---- Drawer -------------------------------------------------------------- */

export function ExecutionDrawer({ row, onClose }: { row: SyncHistoryRow; onClose: () => void }) {
  const execId = row.execution_id
  const [summary, setSummary] = useState<ExecutionSummary | null>(null)
  const [tables, setTables] = useState<ExecutionTableRow[]>([])
  const [errors, setErrors] = useState<ExecutionErrorRow[]>([])
  const [loading, setLoading] = useState(true)
  const isRunning = (summary?.status ?? row.status) === 'RUNNING'

  useEffect(() => {
    let alive = true
    const load = async () => {
      const [s, t, e] = await Promise.all([
        syncService.executionSummary(execId),
        syncService.executionTables(execId),
        syncService.executionErrors(execId),
      ])
      if (!alive) return
      setSummary(s)
      setTables(t)
      setErrors(e)
      setLoading(false)
    }
    void load()
    return () => { alive = false }
  }, [execId])

  // Live progress: auto-refresh every 3s while the execution is still running.
  useEffect(() => {
    if (!isRunning) return
    const id = window.setInterval(async () => {
      const [s, t] = await Promise.all([
        syncService.executionSummary(execId),
        syncService.executionTables(execId),
      ])
      setSummary(s)
      setTables(t)
    }, 3000)
    return () => window.clearInterval(id)
  }, [isRunning, execId])

  // Close on Escape.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const s = summary
  const rowsRead = s?.rows_read ?? row.rows_read
  const progress = useMemo(() => {
    if (!isRunning || tables.length === 0) return null
    const done = tables.filter((t) => t.status !== 'RUNNING').length
    return Math.round((done / tables.length) * 100)
  }, [isRunning, tables])

  return (
    <div className="sx-drawer-scrim" onClick={onClose}>
      <aside
        className="sx-drawer"
        role="dialog"
        aria-label={`Execution ${execId}`}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="sx-drawer__head">
          <div className="min-w-0">
            <div className="sx-drawer__crumb">
              Execution {isRunning && <span className="sx-live__dot" />}
            </div>
            <div className="sx-drawer__title" title={execId}>{execId}</div>
          </div>
          <div className="d-flex align-items-center gap-2">
            <SyncStatusBadge status={s?.status ?? row.status} />
            <button type="button" className="sx-drawer__x" onClick={onClose} aria-label="Close">
              <i className="bi bi-x-lg" aria-hidden="true" />
            </button>
          </div>
        </header>

        <div className="sx-drawer__body">
          {loading || !s ? (
            <div className="sx-inline-load">Loading execution details…</div>
          ) : (
            <>
              {isRunning && progress != null && (
                <div className="sx-drawer__section">
                  <div className="sx-live" style={{ marginBottom: '0.5rem' }}>
                    <span className="sx-live__dot" />Live · auto-refreshing every 3s
                  </div>
                  <div className="sx-progress" role="progressbar" aria-valuenow={progress}>
                    <div className="sx-progress__bar sx-progress__bar--anim" style={{ width: `${Math.max(3, progress)}%` }} />
                  </div>
                  <div className="sx-dim" style={{ marginTop: '0.35rem', fontSize: '0.8rem' }}>
                    {progress}% · {tables.filter((t) => t.status !== 'RUNNING').length}/{tables.length} tables
                  </div>
                </div>
              )}

              {/* ---- Summary ---- */}
              <section className="sx-drawer__section">
                <h4 className="sx-drawer__h">Execution Summary</h4>
                <div className="sx-fieldgrid">
                  <Field label="Store">{s.store_name ?? s.store_code ?? '—'}</Field>
                  <Field label="Tenant">{s.tenant_name ?? '—'}</Field>
                  <Field label="Agent Version">{s.agent_version ?? '—'}</Field>
                  <Field label="Sync Mode"><SyncTypeBadge value={s.sync_mode} /></Field>
                  <Field label="Execution Type">{s.execution_type ?? '—'}</Field>
                  <Field label="Duration">{formatDuration(s.duration_seconds)}</Field>
                  <Field label="Started">{formatDateTime(s.started_at)}</Field>
                  <Field label="Completed">{formatDateTime(s.completed_at)}</Field>
                </div>
                <div className="sx-metricrow">
                  <div className="sx-metric"><span>{num(s.table_count)}</span>Tables</div>
                  <div className="sx-metric"><span>{num(rowsRead)}</span>Rows Read</div>
                  <div className="sx-metric"><span>{num(s.rows_inserted)}</span>Inserted</div>
                  <div className="sx-metric"><span>{num(s.rows_updated)}</span>Updated</div>
                  <div className="sx-metric"><span>{num(s.rows_skipped)}</span>Skipped</div>
                  <div className={`sx-metric${s.error_count ? ' sx-metric--danger' : ''}`}><span>{num(s.error_count)}</span>Errors</div>
                  <div className="sx-metric"><span>{num(s.retry_count)}</span>Retries</div>
                </div>
              </section>

              {/* ---- Timeline ---- */}
              <section className="sx-drawer__section">
                <h4 className="sx-drawer__h">Timeline</h4>
                <Timeline summary={s} />
              </section>

              {/* ---- Table execution grid ---- */}
              <section className="sx-drawer__section">
                <h4 className="sx-drawer__h">
                  Table Execution <span className="sx-card__sub">{tables.length} tables</span>
                </h4>
                {tables.length === 0 ? (
                  <div className="sx-inline-load sx-dim">No table records for this execution.</div>
                ) : (
                  <SxTable>
                    <thead>
                      <tr>
                        <th>#</th><th>Table</th><th>Direction</th>
                        <th className="sx-num">Read</th><th className="sx-num">Uploaded</th>
                        <th className="sx-num">Inserted</th><th className="sx-num">Updated</th>
                        <th className="sx-num">Skipped</th><th>Duration</th><th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {tables.map((t) => <TableRow key={`${t.order}-${t.table_name}`} execId={execId} row={t} />)}
                    </tbody>
                  </SxTable>
                )}
                <div className="sx-dim" style={{ fontSize: '0.78rem', marginTop: '0.4rem' }}>
                  Click a table row to expand its chunk detail.
                </div>
              </section>

              {/* ---- Error log ---- */}
              {errors.length > 0 && (
                <section className="sx-drawer__section">
                  <h4 className="sx-drawer__h sx-drawer__h--danger">
                    Error Log <SxChip tone="danger">{errors.length}</SxChip>
                  </h4>
                  <div className="sx-errlist">
                    {errors.map((e, i) => (
                      <div key={i} className="sx-err">
                        <div className="sx-err__head">
                          <span className="sx-strong">{e.table_name}</span>
                          <span className="sx-dim">chunk #{e.chunk_no}</span>
                          {e.retry_count > 0 && <SxChip tone="warning">retry ×{e.retry_count}</SxChip>}
                          <span className="sx-dim ms-auto">{formatDateTime(e.completed_at ?? e.started_at)}</span>
                        </div>
                        <pre className="sx-err__msg">{e.error_message ?? 'No message recorded.'}</pre>
                      </div>
                    ))}
                  </div>
                </section>
              )}
            </>
          )}
        </div>
      </aside>
    </div>
  )
}
