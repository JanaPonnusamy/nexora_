import { useEffect, useState } from 'react'
import { procurementService } from '../../services/procurementService'
import type { SupplierReplyPreview } from '../../types/procurement'
import { num } from '../stock/format'

const STATUS_LABEL: Record<string, string> = {
  available: 'Available',
  partial: 'Partial',
  not_available: 'Not Available',
}

/**
 * Supplier Reply import — the supplier's completed Export Document comes
 * back with Status (Available / Partial / Not Available) + Available Qty
 * filled in. Rows are matched to live assignments via the sheet's hidden
 * Assignment ID column (not by product name/order, which the supplier may
 * have edited). Applying a Partial/Not Available row rolls its shortfall
 * into the existing Pending tab — no separate reconciliation UI needed.
 */
export function SupplierReplyImportDialog({
  tenantId,
  refreshId,
  file,
  actingUser,
  onClose,
  onImported,
  notify,
}: {
  tenantId: string
  refreshId: string
  file: File
  actingUser: string
  onClose: () => void
  onImported: (result: { applied: number; skipped: number }) => void
  notify: (kind: 'success' | 'danger', text: string) => void
}) {
  const [preview, setPreview] = useState<SupplierReplyPreview | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    setLoading(true)
    procurementService
      .previewSupplierReply(tenantId, refreshId, file)
      .then((p) => { if (live) setPreview(p) })
      .catch((e) => live && setError(e instanceof Error ? e.message : 'Could not read the file'))
      .finally(() => live && setLoading(false))
    return () => { live = false }
  }, [tenantId, refreshId, file])

  const applicableRows = (preview?.rows ?? []).filter((r) => r.applicable)

  const doImport = async () => {
    if (applicableRows.length === 0) return
    setBusy(true)
    setError(null)
    try {
      const result = await procurementService.importSupplierReply(
        tenantId,
        refreshId,
        applicableRows.map((r) => ({ assignment_id: r.assignment_id, status: r.status, available_qty: r.available_qty })),
        actingUser || null,
      )
      notify('success', `Applied ${result.applied} repl${result.applied === 1 ? 'y' : 'ies'}${result.skipped ? ` · ${result.skipped} skipped` : ''}`)
      onImported(result)
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Import failed')
      setBusy(false)
    }
  }

  return (
    <div className="pm-drawer__backdrop" style={{ zIndex: 1060 }} onClick={onClose}>
      <div className="pm-import" role="dialog" aria-label="Import supplier reply" onClick={(e) => e.stopPropagation()}>
        <header className="pm-import__head">
          <div>
            <h5 className="mb-0"><i className="bi bi-envelope-arrow-down me-2" />Import Supplier Reply</h5>
            <div className="pm-import__sub">{file.name}</div>
          </div>
          <button className="btn-close" aria-label="Close" onClick={onClose} />
        </header>

        {loading ? (
          <div className="pm-import__msg">Reading the file…</div>
        ) : error ? (
          <div className="pm-import__msg pm-import__msg--err">{error}</div>
        ) : !preview || preview.rows.length === 0 ? (
          <div className="pm-import__msg">No rows found in this sheet.</div>
        ) : (
          <>
            <div className="pm-import__hint">
              {applicableRows.length} of {preview.rows.length} row(s) will be applied. Not Available / Partial rows
              roll their shortfall into the Pending tab.
            </div>
            <div className="pm-import__samplewrap" style={{ maxHeight: 360 }}>
              <table className="pm-import__sample">
                <thead>
                  <tr>
                    <th>Product</th>
                    <th>Status</th>
                    <th className="sx-num">Assigned Qty</th>
                    <th className="sx-num">Available Qty</th>
                    <th>Note</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.rows.map((r) => (
                    <tr key={r.assignment_id} style={{ opacity: r.applicable ? 1 : 0.5 }}>
                      <td>{r.product_name ?? r.product_code ?? r.assignment_id}</td>
                      <td>{r.status ? STATUS_LABEL[r.status] : <span className="sx-dim">—</span>}</td>
                      <td className="sx-num">{r.assigned_qty != null ? num(r.assigned_qty) : '—'}</td>
                      <td className="sx-num">{r.available_qty != null ? num(r.available_qty) : '—'}</td>
                      <td>{r.warning && <span className="pm-import__warn">{r.warning}</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}

        <footer className="pm-import__foot">
          <span className="sx-dim">{applicableRows.length} applicable row(s)</span>
          <div className="pm-import__actions">
            <button className="pm-btn pm-btn--ghost" onClick={onClose}>Cancel</button>
            <button className="pm-btn pm-btn--primary" onClick={doImport} disabled={busy || applicableRows.length === 0}>
              <i className="bi bi-check2-circle" /> {busy ? 'Applying…' : 'Apply'}
            </button>
          </div>
        </footer>
      </div>
    </div>
  )
}
