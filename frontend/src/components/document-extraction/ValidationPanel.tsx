import { useState } from 'react'
import type { ValidationFinding } from '../../types/documentExtraction'
import { statusLabel, validationLabel, VALIDATION_BADGE } from './statusLabels'

interface ValidationPanelProps {
  status: string
  validationStatus: string
  findings: ValidationFinding[]
  saving?: boolean
  onComplete: () => void | Promise<void>
  onDelete: () => void | Promise<void>
}

/** The bottom bar of the workspace — the operator's last stop before moving
 *  to the next invoice, so it answers one question: is this safe to save?
 *  Unresolved errors don't hard-block Save (the backend accepts a forced
 *  save with confirmation — see ReviewPage's onComplete), they just make the
 *  risk visible before the click. */
export function ValidationPanel({ status, validationStatus, findings, saving, onComplete, onDelete }: ValidationPanelProps) {
  const [expanded, setExpanded] = useState(false)
  const errors = findings.filter((f) => f.severity === 'ERROR')
  const warnings = findings.filter((f) => f.severity === 'WARNING')
  const isSaved = status === 'SAVED' || status === 'EXPORTED'

  return (
    <div className="dx-valbar">
      <div className="dx-valbar__status">
        <span className={`badge ${VALIDATION_BADGE[validationStatus] ?? 'text-bg-secondary'}`}>
          {validationLabel(validationStatus)}
        </span>
        {errors.length > 0 && <span className="text-danger small"><i className="bi bi-x-octagon-fill me-1" />{errors.length} error{errors.length === 1 ? '' : 's'}</span>}
        {warnings.length > 0 && <span className="text-warning-emphasis small"><i className="bi bi-exclamation-triangle-fill me-1" />{warnings.length} warning{warnings.length === 1 ? '' : 's'}</span>}
        {findings.length === 0 && <span className="text-success small"><i className="bi bi-check-circle-fill me-1" />All checks passed</span>}
        {findings.length > 0 && (
          <button type="button" className="btn btn-link btn-sm p-0 ms-2" onClick={() => setExpanded((e) => !e)}>
            {expanded ? 'Hide details' : 'Show details'}
          </button>
        )}
      </div>

      {expanded && findings.length > 0 && (
        <ul className="dx-valbar__list">
          {[...errors, ...warnings].map((f, idx) => (
            <li key={`${f.rule_code}-${idx}`}>
              <span className={`badge ${f.severity === 'ERROR' ? 'text-bg-danger' : 'text-bg-warning'} me-2`}>{f.severity}</span>
              {f.message}
              {f.field && <span className="text-muted"> ({f.field})</span>}
            </li>
          ))}
        </ul>
      )}

      <div className="dx-valbar__actions">
        <span className="text-muted small">{statusLabel(status)}</span>
        <button type="button" className="btn btn-outline-danger btn-sm" disabled={saving} onClick={() => void onDelete()}>
          <i className="bi bi-trash3 me-1" />Delete
        </button>
        <button
          type="button" className="btn btn-success btn-sm"
          disabled={saving || isSaved}
          title="Ctrl+S"
          onClick={() => void onComplete()}
        >
          <i className="bi bi-check2-circle me-1" />
          {isSaved ? 'Saved' : saving ? 'Saving…' : 'Save & Complete'}
          {!isSaved && <span className="dx-valbar__kbd">Ctrl+S</span>}
        </button>
      </div>
    </div>
  )
}
