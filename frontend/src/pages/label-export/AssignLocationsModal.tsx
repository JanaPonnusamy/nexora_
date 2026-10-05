import { useMemo, useState } from 'react'
import { labelExporterService } from '../../services/labelExporterService'
import type { AssignmentMode, AssignmentType, LabelAssignResult } from '../../types/labelExporter'

export interface AssignableProduct {
  product_code: string
  product_name: string
  /** Current/corrected unit — assignment always uses this, never the old unit (spec §2/§16). */
  currentUnit: string
}

/**
 * Location-assignment dialog (spec §12–§18). Operates on the Review=Y & Pending
 * products. The two location MODES are explicit and never guessed:
 *   • Continue Existing Locations — fill the last partial box first (spec §14).
 *   • New Label for Entire Letter — ignore existing boxes, fresh sequence (spec §15).
 * SYP auto-buckets by first letter (spec §16); Single Product Box gives one box
 * per product (spec §17). The backend recomputes and validates every plan — the
 * UI only previews and commits, it never allocates boxes itself.
 */
export function AssignLocationsModal({
  tenantId,
  storeId,
  products,
  defaultLetter,
  canCommit,
  onClose,
  onCommitted,
}: {
  tenantId: string
  storeId: string
  products: AssignableProduct[]
  defaultLetter: string
  canCommit: boolean
  onClose: () => void
  onCommitted: (result: LabelAssignResult) => void
}) {
  const units = useMemo(() => {
    const set = new Set(products.map((p) => (p.currentUnit || '').toUpperCase()).filter(Boolean))
    return Array.from(set).sort()
  }, [products])

  const [unit, setUnit] = useState(units[0] ?? '')
  const [assignmentType, setAssignmentType] = useState<AssignmentType>('standard_box')
  const [mode, setMode] = useState<AssignmentMode>('continue')
  const [letter, setLetter] = useState('')
  const [startNumber, setStartNumber] = useState('1')
  const [preview, setPreview] = useState<LabelAssignResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [committed, setCommitted] = useState(false)

  const productsForUnit = useMemo(
    () => products.filter((p) => (p.currentUnit || '').toUpperCase() === unit),
    [products, unit],
  )

  const effectiveLetter = useMemo(() => {
    if (letter) return letter
    if (defaultLetter) return defaultLetter.toUpperCase().slice(0, 1)
    const firstName = productsForUnit[0]?.product_name?.trim() ?? ''
    return firstName ? firstName[0].toUpperCase() : ''
  }, [letter, defaultLetter, productsForUnit])

  const isSyp = assignmentType === 'standard_box' && unit === 'SYP'
  const isTab = assignmentType === 'standard_box' && unit === 'TAB'
  const isSingle = assignmentType === 'single_product_box'
  const needsLetter = isTab || isSingle
  // CAP/LOT/PACK/… have no automatic standard-box rule — the operator must use
  // Single Product Box (or assign manually), so surface that instead of erroring.
  const noAutoRule = assignmentType === 'standard_box' && !isSyp && !isTab

  const effectiveMode: AssignmentMode = isSingle ? 'single' : isSyp ? 'new_label' : mode

  function buildRequest() {
    return {
      unit,
      mode: effectiveMode,
      assignment_type: assignmentType,
      letter: needsLetter ? effectiveLetter : '',
      product_codes: productsForUnit.map((p) => p.product_code),
      start_number: Number(startNumber) || 1,
    }
  }

  async function runPreview() {
    setError(null)
    setBusy(true)
    try {
      const result = await labelExporterService.previewAssignment(tenantId, storeId, buildRequest())
      setPreview(result)
    } catch (err) {
      setPreview(null)
      setError(err instanceof Error ? err.message : 'Failed to build preview')
    } finally {
      setBusy(false)
    }
  }

  async function runCommit() {
    setError(null)
    setBusy(true)
    try {
      const result = await labelExporterService.commitAssignment(tenantId, storeId, buildRequest())
      setCommitted(true)
      onCommitted(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to commit assignment')
    } finally {
      setBusy(false)
    }
  }

  const canPreview = productsForUnit.length > 0 && !noAutoRule && (!needsLetter || !!effectiveLetter) && !busy

  return (
    <div className="lx-modal-backdrop" onClick={onClose}>
      <div className="lx-modal" role="dialog" aria-modal="true" aria-label="Assign locations" onClick={(e) => e.stopPropagation()}>
        <div className="lx-modal__head">
          <strong>Assign Locations</strong>
          <button type="button" className="btn-close" aria-label="Close" onClick={onClose} />
        </div>

        <div className="lx-modal__body">
          <div className="lx-assign-controls">
            <label className="lx-assign-field">
              <span>Unit</span>
              <select className="form-select form-select-sm" value={unit} onChange={(e) => { setUnit(e.target.value); setPreview(null) }}>
                {units.length === 0 && <option value="">—</option>}
                {units.map((u) => (
                  <option key={u} value={u}>{u} ({products.filter((p) => (p.currentUnit || '').toUpperCase() === u).length})</option>
                ))}
              </select>
            </label>

            <label className="lx-assign-field">
              <span>Box type</span>
              <select
                className="form-select form-select-sm"
                value={assignmentType}
                onChange={(e) => { setAssignmentType(e.target.value as AssignmentType); setPreview(null) }}
              >
                <option value="standard_box">Standard Box</option>
                <option value="single_product_box">Single Product Box (1 per box)</option>
              </select>
            </label>

            {isTab && (
              <label className="lx-assign-field">
                <span>Mode</span>
                <select className="form-select form-select-sm" value={mode} onChange={(e) => { setMode(e.target.value as AssignmentMode); setPreview(null) }}>
                  <option value="continue">Continue Existing Locations</option>
                  <option value="new_label">New Label for Entire Letter</option>
                </select>
              </label>
            )}

            {needsLetter && (
              <label className="lx-assign-field lx-assign-field--letter">
                <span>Letter</span>
                <input
                  className="form-control form-control-sm"
                  value={effectiveLetter}
                  maxLength={1}
                  onChange={(e) => { setLetter(e.target.value.replace(/[^a-z]/gi, '').toUpperCase().slice(0, 1)); setPreview(null) }}
                />
              </label>
            )}

            {isTab && mode === 'new_label' && (
              <label className="lx-assign-field lx-assign-field--letter">
                <span>Start #</span>
                <input
                  className="form-control form-control-sm"
                  value={startNumber}
                  onChange={(e) => { setStartNumber(e.target.value.replace(/[^0-9]/g, '') || '1'); setPreview(null) }}
                />
              </label>
            )}

            <button className="btn btn-sm btn-primary lx-assign-preview-btn" disabled={!canPreview} onClick={() => void runPreview()}>
              {busy && !committed ? 'Working…' : 'Preview'}
            </button>
          </div>

          <div className="lx-assign-hint">
            {isSyp && <span>SYP auto-buckets by first letter of product name (SYPA, SYPB…). Letter &amp; mode are not used.</span>}
            {isTab && mode === 'continue' && <span>Fills the last partial box for letter <strong>{effectiveLetter || '?'}</strong> to 7 first, then opens new boxes.</span>}
            {isTab && mode === 'new_label' && <span>Ignores existing boxes: fresh sequence from {effectiveLetter || '?'}{String(Number(startNumber) || 1).padStart(3, '0')}, 7 per box, name order.</span>}
            {isSingle && <span>Each product gets its own box, continuing after the highest existing box for {effectiveLetter || '?'}.</span>}
            {noAutoRule && <span className="text-danger">No automatic rule for unit “{unit}”. Use Single Product Box, or assign manually.</span>}
          </div>

          {error && <div className="alert alert-danger py-2 small mb-0">{error}</div>}

          {preview && (
            <div className="lx-assign-preview">
              <div className="lx-assign-preview__boxes">
                <table className="table table-sm mb-0">
                  <thead className="table-light">
                    <tr><th>Box</th><th className="text-end">Existing</th><th className="text-end">New</th><th className="text-end">Total</th><th className="text-end">Cap</th></tr>
                  </thead>
                  <tbody>
                    {preview.boxes.map((b) => (
                      <tr key={b.box}>
                        <td className="fw-semibold">{b.box}</td>
                        <td className="text-end">{b.existing || '—'}</td>
                        <td className="text-end text-success">+{b.added}</td>
                        <td className="text-end">{b.total}</td>
                        <td className="text-end text-muted">{b.capacity ?? '∞'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="lx-assign-preview__items">
                <table className="table table-sm mb-0">
                  <thead className="table-light">
                    <tr><th>Product</th><th>Box</th><th className="text-end">Slot</th></tr>
                  </thead>
                  <tbody>
                    {preview.assignments.map((a) => (
                      <tr key={a.product_code}>
                        <td>{a.product_name}</td>
                        <td className="fw-semibold">{a.box}</td>
                        <td className="text-end">{a.slot}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        <div className="lx-modal__foot">
          <span className="text-muted small">
            {productsForUnit.length} {unit || '?'} product(s) selected
            {preview ? ` · ${preview.assigned_count} to assign across ${preview.boxes.length} box(es)` : ''}
          </span>
          <div className="d-flex gap-2">
            <button className="btn btn-sm btn-outline-secondary" onClick={onClose}>Cancel</button>
            {canCommit ? (
              <button className="btn btn-sm btn-success" disabled={!preview || busy || committed} onClick={() => void runCommit()}>
                {committed ? '✓ Assigned' : busy ? 'Committing…' : 'Commit assignment'}
              </button>
            ) : (
              <span className="text-muted small align-self-center">Commit is a super-admin action</span>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
