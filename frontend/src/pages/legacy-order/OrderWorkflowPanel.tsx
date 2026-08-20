import { useCallback, useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { legacyOrderService } from '../../services/legacyOrderService'
import type { OrderWorkflowAuditEntry, OrderWorkflowSummary } from '../../types/legacyOrder'

interface Props {
  store: string
  refreshToken?: number
  onError: (message: string) => void
  onChange?: (summary: OrderWorkflowSummary) => void
}

const steps = [
  { key: 'generate', label: 'Generate', icon: 'bi-stars', href: '/legacy-order' },
  { key: 'review', label: 'Qty review', icon: 'bi-check2-square', href: '/legacy-order/qty-check' },
  { key: 'supplier', label: 'Assign suppliers', icon: 'bi-people', href: '/legacy-order/workspace' },
  { key: 'finalize', label: 'Finalize', icon: 'bi-lock', href: '/legacy-order/workspace' },
] as const

function stageIndex(summary: OrderWorkflowSummary | null): number {
  if (!summary?.order_id) return 0
  if (summary.status === 'QTY_REVIEW') return 1
  if (summary.status === 'SUPPLIER_ASSIGNMENT') return 2
  return 3
}

function fmt(value: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

export function OrderWorkflowPanel({ store, refreshToken = 0, onError, onChange }: Props) {
  const location = useLocation()
  const [summary, setSummary] = useState<OrderWorkflowSummary | null>(null)
  const [busy, setBusy] = useState(false)
  const [auditOpen, setAuditOpen] = useState(false)
  const [audit, setAudit] = useState<OrderWorkflowAuditEntry[]>([])

  const load = useCallback(() => {
    if (!store) return
    legacyOrderService.orderWorkflow(store)
      .then((next) => { setSummary(next); onChange?.(next) })
      .catch((e: Error) => onError(e.message))
  }, [store, onError, onChange])

  useEffect(() => { load() }, [load, refreshToken])

  const toggleAudit = () => {
    const next = !auditOpen
    setAuditOpen(next)
    if (next && store) {
      legacyOrderService.orderWorkflowAudit(store).then(setAudit).catch((e: Error) => onError(e.message))
    }
  }

  const mutate = (reopen: boolean) => {
    if (!store) return
    const note = reopen
      ? window.prompt('Why is this order being reopened?')
      : window.prompt('Optional finalization note:')
    if (note === null) return
    setBusy(true)
    const call = reopen
      ? legacyOrderService.reopenOrder(store, note)
      : legacyOrderService.finalizeOrder(store, note)
    call.then((next) => { setSummary(next); onChange?.(next) })
      .catch((e: Error) => onError(e.message))
      .finally(() => setBusy(false))
  }

  const active = stageIndex(summary)
  const total = summary?.total_lines ?? 0
  const completed = (summary?.qty_reviewed ?? 0) + (summary?.assigned_lines ?? 0) + (summary?.closed_lines ?? 0)
  const progress = total ? Math.min(100, Math.round((completed / Math.max(total * 2, 1)) * 100)) : 0

  return (
    <section className="lo-workflow" aria-label="Order workflow">
      <div className="lo-workflow-head">
        <div>
          <span className="lo-eyebrow">Current order</span>
          <strong>{summary?.order_id ? `#${summary.order_id} · ${store}` : `${store || 'Select a store'} · no generated order`}</strong>
        </div>
        <div className="lo-workflow-actions">
          {summary?.status === 'FINALIZED' ? (
            <button type="button" className="lo-btn" disabled={busy} onClick={() => mutate(true)}><i className="bi bi-unlock" /> Reopen</button>
          ) : (
            <button type="button" className="lo-btn lo-btn-primary" disabled={busy || !summary?.ready} title={summary?.ready ? 'Lock this order for downstream processing' : 'Complete quantity review and supplier assignment first'} onClick={() => mutate(false)}><i className="bi bi-lock" /> Finalize order</button>
          )}
          <button type="button" className="lo-btn" disabled={!summary?.order_id} onClick={toggleAudit}><i className="bi bi-clock-history" /> Activity</button>
        </div>
      </div>

      <div className="lo-workflow-steps">
        {steps.map((step, index) => {
          const current = index === active
          const done = index < active || summary?.status === 'FINALIZED'
          return (
            <Link key={step.key} to={step.href} className={`${current ? 'is-current' : ''}${done ? ' is-done' : ''}${location.pathname === step.href ? ' is-page' : ''}`}>
              <span><i className={`bi ${done ? 'bi-check-lg' : step.icon}`} /></span>
              <small>Step {index + 1}</small>
              <strong>{step.label}</strong>
            </Link>
          )
        })}
      </div>

      <div className="lo-workflow-metrics">
        <span><strong>{summary?.qty_pending ?? 0}</strong> qty pending</span>
        <span><strong>{summary?.unassigned_lines ?? 0}</strong> supplier pending</span>
        <span><strong>{summary?.assigned_lines ?? 0}</strong> assigned</span>
        <span><strong>{summary?.supplier_count ?? 0}</strong> suppliers</span>
        <span><strong>{summary?.assigned_qty ?? 0}</strong> units</span>
        <span><strong>₹{(summary?.assigned_value ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}</strong> value</span>
        <div className="lo-workflow-progress" title={`${progress}% workflow progress`}><span style={{ width: `${progress}%` }} /></div>
        <em className={`lo-workflow-status is-${(summary?.status ?? 'DRAFT').toLowerCase()}`}>{(summary?.status ?? 'DRAFT').replaceAll('_', ' ')}</em>
      </div>

      {summary?.finalized_at && <p className="lo-workflow-finalized">Finalized {fmt(summary.finalized_at)} by {summary.updated_by || 'unknown user'}{summary.note ? ` · ${summary.note}` : ''}</p>}

      {auditOpen && (
        <div className="lo-workflow-audit">
          {audit.map((entry) => (
            <div key={entry.AuditId}>
              <i className="bi bi-dot" />
              <span><strong>{entry.Action.replaceAll('_', ' ')}</strong>{entry.ProductCode ? ` · product ${entry.ProductCode}` : ''}</span>
              <small>{entry.Actor || 'system'} · {fmt(entry.CreatedAt)}</small>
            </div>
          ))}
          {!audit.length && <p className="lo-empty">No workflow activity recorded yet.</p>}
        </div>
      )}
    </section>
  )
}
