import { useEffect, useState } from 'react'
import { procurementService } from '../../services/procurementService'
import { ApiError } from '../../services/apiClient'
import { EmptyState } from '../common/EmptyState'
import { ErrorState } from '../common/ErrorState'
import type { VplHistoryBatch, VplHistoryDetail } from '../../types/procurement'
import { date } from '../stock/format'
import '../stock/stock-ui.css'

/**
 * Read-only VPL working-line history, latest 10 batches for the selected
 * store. Backed by `backend/modules/procurement/vpl_history.py` —
 * process-memory only (migration 0027 is not applied; this list resets
 * empty on every backend restart), and NOT fed by anything the live
 * Purchase Manager does today — the grid never opens a working cycle or
 * calls refresh through this API, so this is ordinarily empty until some
 * other caller opts a store cycle into it. Server requires
 * PROCUREMENT_ADMIN, stricter than the PROCUREMENT_WORKSPACE capability
 * that gates the rest of this page, so a 403 here is expected for some
 * users and is shown as a plain explanation, not an error banner.
 *
 * Historical rows are never editable from here — there is no save path in
 * this component by design.
 */
export function VplHistoryPanel({
  tenantId,
  storeId,
  onClose,
}: {
  tenantId: string
  storeId: string
  onClose: () => void
}) {
  const [headers, setHeaders] = useState<VplHistoryBatch[] | null>(null)
  const [total, setTotal] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [forbidden, setForbidden] = useState(false)
  const [selected, setSelected] = useState<VplHistoryDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailError, setDetailError] = useState<string | null>(null)

  const load = () => {
    setError(null)
    setForbidden(false)
    setHeaders(null)
    procurementService
      .vplHistoryList(tenantId, storeId, 10)
      .then((body) => {
        setHeaders(body.headers)
        setTotal(body.total)
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 403) {
          setForbidden(true)
          setHeaders([])
          return
        }
        setError(err instanceof ApiError ? err.message : 'VPL history could not be loaded.')
        setHeaders([])
      })
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId, storeId])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (selected) setSelected(null)
        else onClose()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [selected, onClose])

  const openBatch = (historyId: string) => {
    setDetailError(null)
    setDetailLoading(true)
    procurementService
      .vplHistoryDetail(historyId)
      .then((body) => setSelected(body))
      .catch((err) => setDetailError(err instanceof ApiError ? err.message : 'That batch could not be opened.'))
      .finally(() => setDetailLoading(false))
  }

  return (
    <>
      <div className="pm-modal__backdrop" onClick={selected ? () => setSelected(null) : onClose} />
      <div className="pm-modal pm-modal--wide" role="dialog" aria-label="VPL history">
        <header className="pm-drawer__head">
          <div>
            <h5 className="mb-0">
              <i className="bi bi-clock-history me-2" />
              VPL History
              {selected && <span className="text-muted small ms-2">— batch detail</span>}
            </h5>
            <div className="small text-muted">
              Read-only archive. Process-memory only — migration 0027 is not applied, and nothing in this
              screen's live refresh flow writes to it yet.
            </div>
          </div>
          <button className="btn-close" aria-label="Close" onClick={selected ? () => setSelected(null) : onClose} />
        </header>

        <div className="pm-modal__body">
          {selected ? (
            <BatchDetail detail={selected} onBack={() => setSelected(null)} />
          ) : forbidden ? (
            <EmptyState
              icon="bi-shield-lock"
              title="Admin access required"
              description="VPL history requires the PROCUREMENT_ADMIN capability. Ask an administrator to open it, or request access."
            />
          ) : error ? (
            <ErrorState title="VPL history" description={error} onRetry={load} />
          ) : headers === null ? (
            <div className="pm-dsec__hint">Loading…</div>
          ) : headers.length === 0 ? (
            <EmptyState
              icon="bi-inbox"
              title="No archived batches"
              description="This store has no VPL history yet. History is only created when a refresh is run through the VPL working-line workflow — the live Purchase Manager does not use this path today."
            />
          ) : (
            <>
              <div className="small text-muted mb-2">
                Showing latest {headers.length} of {total} archived batch{total === 1 ? '' : 'es'}.
              </div>
              {detailError && <ErrorState title="Batch detail" description={detailError} onRetry={undefined} />}
              <div className="pm-minitable-wrap">
                <table className="pm-minitable pm-minitable--click">
                  <thead>
                    <tr>
                      <th>Created</th>
                      <th>Cycle</th>
                      <th>Source refresh</th>
                      <th>Rule snapshot</th>
                      <th className="sx-num">Lines</th>
                      <th>Created by</th>
                    </tr>
                  </thead>
                  <tbody>
                    {headers.map((row) => (
                      <tr
                        key={row.history_id}
                        onClick={() => openBatch(row.history_id)}
                        title="Open batch (read-only)"
                        aria-busy={detailLoading}
                      >
                        <td className="sx-dim">{date(row.created_at)}</td>
                        <td>{row.cycle_id}</td>
                        <td className="sx-dim">{row.source_refresh_id}</td>
                        <td>{row.rule_snapshot_id ?? '—'}</td>
                        <td className="sx-num">{row.line_count}</td>
                        <td>{row.created_by}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      </div>
    </>
  )
}

function BatchDetail({ detail, onBack }: { detail: VplHistoryDetail; onBack: () => void }) {
  return (
    <>
      <div className="d-flex align-items-center mb-2">
        <button className="pm-btn pm-btn--ghost" onClick={onBack}>
          <i className="bi bi-arrow-left me-1" /> Back to batches
        </button>
        <span className="small text-muted ms-3">
          Archived {date(detail.created_at)} · cycle {detail.cycle_id} · {detail.lines.length} line
          {detail.lines.length === 1 ? '' : 's'}
        </span>
      </div>
      {detail.lines.length === 0 ? (
        <div className="pm-dsec__hint">This batch has no lines.</div>
      ) : (
        <div className="pm-minitable-wrap">
          <table className="pm-minitable">
            <thead>
              <tr>
                <th>Product code</th>
                <th className="sx-num">Suggested</th>
                <th className="sx-num">Final</th>
                <th>Supplier</th>
                <th>Carried forward</th>
                <th>Rare confirmed</th>
                <th>Reviewed</th>
                <th className="sx-num">Version</th>
              </tr>
            </thead>
            <tbody>
              {detail.lines.map((line) => (
                <tr key={line.product_code}>
                  <td>{line.product_code}</td>
                  <td className="sx-num">{line.suggested_qty ?? '—'}</td>
                  <td className="sx-num">{line.final_qty ?? '—'}</td>
                  <td>{line.supplier_code ?? '—'}</td>
                  <td>{line.carried_forward ? 'Yes' : 'No'}</td>
                  <td>{line.rare_confirmed ? 'Yes' : 'No'}</td>
                  <td className="sx-dim">{line.reviewed_at ? date(line.reviewed_at) : '—'}</td>
                  <td className="sx-num">{line.row_version}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
