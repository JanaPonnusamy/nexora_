import { useEffect, useState } from 'react'
import { api } from '../../services/apiClient'
import { documentExtractionService } from '../../services/documentExtractionService'
import { useActingUser } from '../../hooks/useActingUser'
import { useAuthorizedImage } from '../../hooks/useAuthorizedImage'
import type { CorrectionEntry, ImportDetail } from '../../types/documentExtraction'
import { headerHighlights } from './reviewChecks'

interface HistoryDetailPanelProps {
  importId: number
  onChanged: () => void
}

const REPROCESS_STAGES = ['preprocessing', 'ocr', 'extraction', 'validation'] as const

export function HistoryDetailPanel({ importId, onChanged }: HistoryDetailPanelProps) {
  const actor = useActingUser()
  const [detail, setDetail] = useState<ImportDetail | null>(null)
  const [corrections, setCorrections] = useState<CorrectionEntry[]>([])
  const [error, setError] = useState<string | null>(null)
  const [fromStage, setFromStage] = useState<(typeof REPROCESS_STAGES)[number]>('ocr')
  const [busy, setBusy] = useState(false)

  const original = useAuthorizedImage(documentExtractionService.originalImagePath(importId))
  const preview = useAuthorizedImage(documentExtractionService.previewImagePath(importId))

  function load() {
    setError(null)
    Promise.all([
      documentExtractionService.importDetail(importId),
      documentExtractionService.corrections(importId),
    ])
      .then(([d, c]) => {
        setDetail(d)
        setCorrections(c.items)
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load import'))
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [importId])

  async function handleReprocess() {
    setBusy(true)
    try {
      await documentExtractionService.reprocess(importId, fromStage, actor)
      load()
      onChanged()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Reprocess failed')
    } finally {
      setBusy(false)
    }
  }

  async function handleDelete() {
    if (!window.confirm('Delete this import? It will be hidden from lists but not physically removed.')) return
    setBusy(true)
    try {
      await documentExtractionService.deleteImport(importId, actor)
      onChanged()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Delete failed')
    } finally {
      setBusy(false)
    }
  }

  async function handleExportAgain(format: 'xlsx' | 'csv') {
    setBusy(true)
    try {
      const result = await documentExtractionService.exportImports([importId], format, actor)
      const blob = await api.blob(result.download_url)
      const objectUrl = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = objectUrl
      link.download = `${result.export_batch_id}.${format}`
      link.click()
      URL.revokeObjectURL(objectUrl)
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Export failed')
    } finally {
      setBusy(false)
    }
  }

  if (error) return <div className="alert alert-danger">{error}</div>
  if (!detail) return <p className="text-muted small">Loading…</p>

  const header = detail.import
  const highlights = headerHighlights(header)

  return (
    <div className="border rounded p-3">
      <div className="d-flex justify-content-between align-items-start mb-3">
        <div>
          <h5 className="mb-0">Import #{header.import_id} — {header.invoice_number ?? 'no invoice #'}</h5>
          <div className="text-muted small">
            {header.supplier_name ?? 'Unknown Supplier'} · Status: {header.status} · Validation: {header.validation_status}
          </div>
          {highlights.length > 0 && (
            <div className="mt-1">
              {highlights.map((h) => <span key={h} className="badge text-bg-warning me-1">{h}</span>)}
            </div>
          )}
        </div>
        <div className="d-flex gap-2 align-items-center">
          <select
            className="form-select form-select-sm" value={fromStage}
            onChange={(e) => setFromStage(e.target.value as (typeof REPROCESS_STAGES)[number])}
          >
            {REPROCESS_STAGES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <button type="button" className="btn btn-outline-secondary btn-sm" disabled={busy} onClick={handleReprocess}>
            Reprocess
          </button>
          <button type="button" className="btn btn-outline-danger btn-sm" disabled={busy} onClick={handleDelete}>
            Delete
          </button>
        </div>
      </div>

      <div className="row g-3 mb-3">
        <div className="col-3">
          <h6 className="text-uppercase text-muted small">Original Image</h6>
          {original.error && <p className="text-muted small">Not available.</p>}
          {!original.error && !original.url && <p className="text-muted small">Loading…</p>}
          {original.url && <img src={original.url} alt="Original" className="img-fluid rounded border" />}
        </div>
        <div className="col-3">
          <h6 className="text-uppercase text-muted small">Processed Image</h6>
          {preview.error && <p className="text-muted small">Not available.</p>}
          {!preview.error && !preview.url && <p className="text-muted small">Loading…</p>}
          {preview.url && <img src={preview.url} alt="Processed" className="img-fluid rounded border" />}
        </div>
        <div className="col-6">
          <h6 className="text-uppercase text-muted small">Extracted Header</h6>
          <dl className="row small mb-0">
            <dt className="col-5">GST Number</dt><dd className="col-7">{header.gst_number ?? '—'}</dd>
            <dt className="col-5">DL Number</dt><dd className="col-7">{header.dl_number ?? '—'}</dd>
            <dt className="col-5">Invoice Date</dt><dd className="col-7">{header.invoice_date ?? '—'}</dd>
            <dt className="col-5">Net Amount</dt><dd className="col-7">{header.net_amount ?? '—'}</dd>
            <dt className="col-5">Item Count</dt><dd className="col-7">{header.item_count ?? detail.items.length}</dd>
          </dl>
        </div>
      </div>

      <h6 className="text-uppercase text-muted small">Products ({detail.items.length})</h6>
      <div className="table-responsive mb-3">
        <table className="table table-sm">
          <thead><tr><th>#</th><th>Product</th><th>Batch</th><th>Qty</th><th>Amount</th></tr></thead>
          <tbody>
            {detail.items.map((item) => (
              <tr key={item.item_id} className={item.is_excluded ? 'text-muted' : undefined}>
                <td>{item.line_number}</td>
                <td>{item.normalized_product_name ?? item.ocr_product_name}</td>
                <td>{item.batch_number ?? '—'}</td>
                <td>{item.quantity ?? '—'}</td>
                <td>{item.amount ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="row g-3">
        <div className="col-6">
          <h6 className="text-uppercase text-muted small">Corrections ({corrections.length})</h6>
          {corrections.length === 0 ? (
            <p className="text-muted small">No manual corrections yet.</p>
          ) : (
            <ul className="list-unstyled small">
              {corrections.map((c) => (
                <li key={c.review_id} className="mb-1">
                  <strong>{c.field_name}</strong>: {c.old_value ?? '—'} → {c.new_value ?? '—'}
                  <span className="text-muted"> ({new Date(c.corrected_at).toLocaleString()})</span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="col-6">
          <h6 className="text-uppercase text-muted small">Export History</h6>
          {detail.exports.length === 0 ? (
            <p className="text-muted small">Never exported.</p>
          ) : (
            <ul className="list-unstyled small">
              {detail.exports.map((e) => (
                <li key={e.export_id} className="mb-1">
                  {e.file_format} · {e.row_count ?? '—'} rows · {new Date(e.exported_at).toLocaleString()}
                </li>
              ))}
            </ul>
          )}
          <div className="d-flex gap-2 align-items-center">
            <button type="button" className="btn btn-primary btn-sm" disabled={busy} onClick={() => handleExportAgain('xlsx')}>
              Export Again (xlsx)
            </button>
            <button type="button" className="btn btn-outline-primary btn-sm" disabled={busy} onClick={() => handleExportAgain('csv')}>
              Export Again (csv)
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
