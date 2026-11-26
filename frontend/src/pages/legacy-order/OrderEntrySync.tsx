// Order Entry's sync view: shown in place of the order card and grids while a
// store's branch -> Order DB sync runs, so the PM only ever sees post-sync
// data. Per-table steps are read from the sync job's own log lines
// ("Starting sync: X" / "Completed: X (N rows)"), not guessed. Same view as
// desktop/supplier-stock-client/src/orderEntrySync.jsx.
import { useEffect, useRef, useState } from 'react'

export interface SyncLogLine {
  stamp: string
  text: string
}

interface SyncStep {
  name: string
  state: 'running' | 'done' | 'failed'
  rows: number | null
}

const START_RE = /^Starting sync:\s*(.+)$/i
const DONE_RE = /^Completed:\s*(.+?)\s*\((\d[\d,]*)\s*rows?\)/i
const FAIL_RE = /fail|error/i

export function syncSteps(log: SyncLogLine[]): SyncStep[] {
  const steps: SyncStep[] = []
  const byName = new Map<string, SyncStep>()
  for (const { text } of log) {
    const start = START_RE.exec(text)
    const done = DONE_RE.exec(text)
    if (start && !byName.has(start[1])) {
      const step: SyncStep = { name: start[1], state: 'running', rows: null }
      byName.set(step.name, step)
      steps.push(step)
    } else if (done && byName.has(done[1])) {
      Object.assign(byName.get(done[1]) as SyncStep, { state: 'done', rows: Number(done[2].replace(/,/g, '')) })
    } else if (FAIL_RE.test(text)) {
      const running = steps.find((s) => s.state === 'running')
      if (running) running.state = 'failed'
    }
  }
  return steps
}

function fmtElapsed(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

export default function OrderEntrySync({
  storeLabel,
  status,
  progress,
  note,
  log,
  startedAt,
  onRetry,
}: {
  storeLabel: string
  status: 'running' | 'failed'
  progress: number
  note: string
  log: SyncLogLine[]
  startedAt: number
  onRetry?: () => void
}) {
  const [now, setNow] = useState(() => Date.now())
  const logRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (status !== 'running') return undefined
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [status])
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [log.length])

  const steps = syncSteps(log)
  const failed = status === 'failed'
  const pct = Math.round(progress)
  return (
    <section className={`poe-card oes${failed ? ' oes--failed' : ''}`} role="status" aria-live="polite">
      <header className="oes-head">
        <div>
          <h3>{failed ? `Sync failed · ${storeLabel}` : `Syncing ${storeLabel}`}</h3>
          <p className="poe-muted">
            {failed ? 'The order data below is as of the last good sync.' : note || 'Connecting to store…'}
          </p>
        </div>
        <div className="oes-figures">
          <strong>{pct}%</strong>
          <span className="poe-muted">{fmtElapsed(now - startedAt)}</span>
        </div>
      </header>

      <div className={`oes-bar${failed ? '' : ' oes-bar--live'}`}>
        <div className="oes-bar-fill" style={{ width: `${Math.max(3, pct)}%` }} />
      </div>

      <ol className="oes-route" aria-label="Sync route">
        {['Store', 'Nexora', 'Order DB'].map((hop, i) => (
          <li key={hop} className={pct >= [0, 35, 99][i] ? 'on' : undefined}>
            {hop}
          </li>
        ))}
      </ol>

      <div className="oes-body">
        <ul className="oes-steps">
          {steps.length === 0 && (
            <li className="oes-step running">
              <span className="oes-dot" />
              Connecting to store…
            </li>
          )}
          {steps.map((s) => (
            <li key={s.name} className={`oes-step ${s.state}`}>
              <span className="oes-dot">{s.state === 'done' ? '✓' : s.state === 'failed' ? '✕' : ''}</span>
              <span className="oes-step-name">{s.name}</span>
              <span className="oes-step-rows">
                {s.state === 'done' ? `${(s.rows ?? 0).toLocaleString()} rows` : s.state === 'failed' ? 'failed' : 'syncing…'}
              </span>
            </li>
          ))}
        </ul>
        <div className="oes-log" ref={logRef}>
          {log.map((line, i) => (
            <div key={i} className="oes-log-line">
              <span>{line.stamp}</span>
              {line.text}
            </div>
          ))}
        </div>
      </div>

      {failed && onRetry && (
        <div className="oes-actions">
          <button type="button" className="primary-button" onClick={onRetry}>
            Retry sync
          </button>
        </div>
      )}
    </section>
  )
}
