import { useState } from 'react'
import { documentExtractionService } from '../../services/documentExtractionService'
import { useAuthorizedImage } from '../../hooks/useAuthorizedImage'

interface InvoiceViewerProps {
  importId: number
  pageCount: number | null
  hasPreview: boolean
}

const ZOOM_STEPS = [0.5, 0.75, 1, 1.25, 1.5, 2, 2.5, 3]

/** Left-pane source-of-truth image — the operator cross-checks every
 *  extracted field against this, so it stays visible and independently
 *  scrollable/zoomable the entire time the workspace is open. */
export function InvoiceViewer({ importId, pageCount, hasPreview }: InvoiceViewerProps) {
  const [page, setPage] = useState(1)
  const [zoomIdx, setZoomIdx] = useState(2) // 1x
  const [showOriginal, setShowOriginal] = useState(false)

  const totalPages = pageCount ?? 1
  const path = showOriginal
    ? documentExtractionService.originalImagePath(importId, page)
    : hasPreview
      ? documentExtractionService.previewImagePath(importId, page)
      : documentExtractionService.originalImagePath(importId, page)
  const { url, error } = useAuthorizedImage(path)
  const zoom = ZOOM_STEPS[zoomIdx]

  return (
    <div className="dx-viewer">
      <div className="dx-viewer__toolbar">
        <div className="dx-viewer__pager">
          <button type="button" className="btn btn-sm btn-outline-secondary" disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))} title="Previous page">
            <i className="bi bi-chevron-left" />
          </button>
          <span className="dx-viewer__pageno">Page {page} / {totalPages}</span>
          <button type="button" className="btn btn-sm btn-outline-secondary" disabled={page >= totalPages}
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))} title="Next page">
            <i className="bi bi-chevron-right" />
          </button>
        </div>
        <div className="dx-viewer__zoom">
          <button type="button" className="btn btn-sm btn-outline-secondary" disabled={zoomIdx <= 0}
            onClick={() => setZoomIdx((z) => Math.max(0, z - 1))} title="Zoom out">
            <i className="bi bi-dash-lg" />
          </button>
          <span className="dx-viewer__zoomval">{Math.round(zoom * 100)}%</span>
          <button type="button" className="btn btn-sm btn-outline-secondary" disabled={zoomIdx >= ZOOM_STEPS.length - 1}
            onClick={() => setZoomIdx((z) => Math.min(ZOOM_STEPS.length - 1, z + 1))} title="Zoom in">
            <i className="bi bi-plus-lg" />
          </button>
          <button type="button" className="btn btn-sm btn-outline-secondary" onClick={() => setZoomIdx(2)} title="Reset zoom">
            <i className="bi bi-aspect-ratio" />
          </button>
        </div>
        {hasPreview && (
          <button type="button" className="btn btn-sm btn-link dx-viewer__toggle" onClick={() => setShowOriginal((s) => !s)}>
            {showOriginal ? 'Show enhanced' : 'Show original'}
          </button>
        )}
      </div>

      <div className="dx-viewer__stage">
        {error && <p className="text-muted small p-3">Image could not be loaded.</p>}
        {!error && !url && <p className="text-muted small p-3">Loading page…</p>}
        {url && (
          <img
            src={url}
            alt={`Invoice page ${page}`}
            className="dx-viewer__img"
            style={{ width: `${zoom * 100}%` }}
          />
        )}
      </div>
    </div>
  )
}
