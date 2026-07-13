import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ErrorState } from '../../components/common/ErrorState'
import { UniGrid, type UniGridColumn, UniLoadingOverlay } from '../../platform/ui'
import { ProcessingQueuePanel } from '../../components/document-extraction/ProcessingQueuePanel'
import { InvoiceViewer } from '../../components/document-extraction/InvoiceViewer'
import { HeaderPanel } from '../../components/document-extraction/HeaderPanel'
import { InvoiceItemsGrid } from '../../components/document-extraction/InvoiceItemsGrid'
import { ValidationPanel } from '../../components/document-extraction/ValidationPanel'
import { documentExtractionService } from '../../services/documentExtractionService'
import { storeService } from '../../services/storeService'
import { useActingUser } from '../../hooks/useActingUser'
import { ApiError } from '../../services/apiClient'
import { keyboardManager } from '../../platform/keyboard/KeyboardManager'
import { statusLabel, STATUS_BADGE } from '../../components/document-extraction/statusLabels'
import type { ImportListRow, ReviewPayload } from '../../types/documentExtraction'
import type { Store } from '../../types/store'
import '../../components/document-extraction/document-extraction.css'

function isTextEditor(el: Element | null): boolean {
  return !!el?.tagName && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA')
}

export default function DocumentExtractionReviewPage() {
  const { importId } = useParams<{ importId?: string }>()
  const navigate = useNavigate()
  const actor = useActingUser()

  const [stores, setStores] = useState<Store[]>([])
  const [storeId, setStoreId] = useState('')
  const [imports, setImports] = useState<ImportListRow[]>([])
  const [review, setReview] = useState<ReviewPayload | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isSaving, setIsSaving] = useState(false)

  const openUploadPickerRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    storeService.list().then((all) => setStores(all.filter((s) => s.is_active))).catch(() => setStores([]))
  }, [])

  useEffect(() => {
    if (!storeId && stores.length > 0) setStoreId(stores[0].store_id)
  }, [stores, storeId])

  const tenantId = useMemo(
    () => stores.find((s) => s.store_id === storeId)?.tenant_id ?? '',
    [stores, storeId],
  )

  const loadImports = useCallback(() => {
    if (!tenantId) return
    documentExtractionService.listImports(tenantId, storeId)
      .then((page) => setImports(page.items))
      .catch(() => setImports([]))
  }, [tenantId, storeId])

  useEffect(() => { loadImports() }, [loadImports])

  const loadReview = useCallback(() => {
    if (!importId) {
      setReview(null)
      return
    }
    setIsLoading(true)
    setError(null)
    documentExtractionService.review(importId)
      .then(setReview)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load import'))
      .finally(() => setIsLoading(false))
  }, [importId])

  useEffect(() => { loadReview() }, [loadReview])

  async function refresh() {
    loadReview()
    loadImports()
  }

  const queueIndex = importId ? imports.findIndex((r) => String(r.import_id) === importId) : -1

  function goToImport(id: number | undefined) {
    if (id == null) return
    navigate(`/document-extraction/review/${id}`)
  }

  function goRelative(dir: 1 | -1) {
    if (imports.length === 0) return
    const from = queueIndex < 0 ? (dir === 1 ? -1 : imports.length) : queueIndex
    const next = imports[from + dir]
    if (next) goToImport(next.import_id)
  }

  // After a save, jump straight to the next invoice still needing attention
  // (skipping already-saved/exported ones) so the operator can keep working
  // the queue without touching the mouse — otherwise every save would dead-
  // end back at the invoice that was just finished.
  function goToNextPending(afterId: number) {
    const startIdx = imports.findIndex((r) => r.import_id === afterId)
    const ordered = imports.filter((r) => r.import_id !== afterId)
    const rotated = startIdx >= 0 ? [...imports.slice(startIdx + 1), ...imports.slice(0, startIdx)] : ordered
    const next = rotated.find((r) => r.status !== 'SAVED' && r.status !== 'EXPORTED')
    if (next) navigate(`/document-extraction/review/${next.import_id}`)
    else navigate('/document-extraction/review')
  }

  async function handleComplete() {
    if (!review) return
    setIsSaving(true)
    try {
      try {
        await documentExtractionService.save(review.import_id, false, actor)
      } catch (e) {
        if (e instanceof ApiError && e.status === 409) {
          const proceed = window.confirm(
            'This invoice still has unresolved validation errors. Save it anyway?',
          )
          if (!proceed) return
          await documentExtractionService.save(review.import_id, true, actor)
        } else {
          throw e
        }
      }
      const savedId = review.import_id
      await refresh()
      goToNextPending(savedId)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setIsSaving(false)
    }
  }

  async function handleDelete() {
    if (!review) return
    if (!window.confirm(`Delete import #${review.import_id}? It will be removed from the queue.`)) return
    setIsSaving(true)
    try {
      await documentExtractionService.deleteImport(review.import_id, actor)
      navigate('/document-extraction/review')
      loadImports()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Delete failed')
    } finally {
      setIsSaving(false)
    }
  }

  // Global shortcuts: Ctrl+S completes the open invoice, Ctrl+U starts a new
  // upload from anywhere in the workspace, PageUp/PageDown walk the queue.
  useEffect(() => {
    const unregisterSave = keyboardManager.register('ctrl+s', (e) => {
      e.preventDefault()
      if (review) void handleComplete()
    })
    const unregisterUpload = keyboardManager.register('ctrl+u', (e) => {
      e.preventDefault()
      if (importId) navigate('/document-extraction/review')
      else openUploadPickerRef.current?.()
    })
    const unregisterNext = keyboardManager.register('pagedown', (e) => {
      if (isTextEditor(document.activeElement)) return
      e.preventDefault()
      goRelative(1)
    })
    const unregisterPrev = keyboardManager.register('pageup', (e) => {
      if (isTextEditor(document.activeElement)) return
      e.preventDefault()
      goRelative(-1)
    })
    return () => {
      unregisterSave()
      unregisterUpload()
      unregisterNext()
      unregisterPrev()
    }
  })

  const queueColumns: UniGridColumn<ImportListRow>[] = [
    { key: 'invoice_number', header: 'Invoice #', render: (r) => r.invoice_number ?? '—' },
    {
      key: 'supplier_name', header: 'Supplier',
      render: (r) => (
        <>
          {r.supplier_name ?? '—'}
          {r.is_supplier_unknown && <span className="badge text-bg-danger ms-1">Unknown</span>}
        </>
      ),
    },
    {
      key: 'status', header: 'Status',
      render: (r) => <span className={`badge ${STATUS_BADGE[r.status] ?? 'text-bg-secondary'}`}>{statusLabel(r.status)}</span>,
    },
    {
      key: 'validation_status', header: 'Validation',
      render: (r) => (
        <span className={`badge ${r.validation_status === 'FAILED' ? 'text-bg-danger' : r.validation_status === 'WARNING' ? 'text-bg-warning' : 'text-bg-secondary'}`}>
          {r.validation_status === 'FAILED' ? 'Errors' : r.validation_status === 'WARNING' ? 'Warnings' : r.validation_status}
        </span>
      ),
    },
    { key: 'net_amount', header: 'Net Amount', align: 'end', render: (r) => r.net_amount != null ? `₹${r.net_amount.toLocaleString('en-IN')}` : '—' },
    { key: 'uploaded_at', header: 'Uploaded', render: (r) => new Date(r.uploaded_at).toLocaleString() },
  ]

  const pendingCount = imports.filter((r) => r.status !== 'SAVED' && r.status !== 'EXPORTED').length
  const unknownSupplierCount = imports.filter((r) => r.is_supplier_unknown).length
  const errorCount = imports.filter((r) => r.validation_status === 'FAILED').length

  return (
    <div className="dx-page">
      <div className="dx-topbar">
        <div className="dx-topbar__brand">
          <i className="bi bi-file-earmark-medical" />
          <span>Document Extraction</span>
        </div>
        <div className="dx-topbar__store">
          <select className="form-select form-select-sm" value={storeId} onChange={(e) => setStoreId(e.target.value)}>
            {stores.map((s) => (
              <option key={s.store_id} value={s.store_id}>{s.store_code} — {s.store_name}</option>
            ))}
          </select>
        </div>
        {importId && (
          <>
            <div className="dx-topbar__jump">
              <select
                className="form-select form-select-sm"
                value={importId ?? ''}
                onChange={(e) => goToImport(Number(e.target.value))}
              >
                <option value="">Jump to invoice…</option>
                {imports.map((row) => (
                  <option key={row.import_id} value={row.import_id}>
                    #{row.import_id} · {row.invoice_number ?? 'no invoice #'} · {row.supplier_name ?? 'Unknown Supplier'}
                  </option>
                ))}
              </select>
            </div>
            <div className="dx-topbar__nav">
              <button type="button" className="btn btn-sm btn-outline-secondary" disabled={queueIndex <= 0} onClick={() => goRelative(-1)} title="Previous invoice (Page Up)">
                <i className="bi bi-chevron-left" />
              </button>
              <button type="button" className="btn btn-sm btn-outline-secondary" disabled={queueIndex < 0 || queueIndex >= imports.length - 1} onClick={() => goRelative(1)} title="Next invoice (Page Down)">
                <i className="bi bi-chevron-right" />
              </button>
            </div>
          </>
        )}
        <div className="dx-topbar__spacer" />
        {importId && (
          <button type="button" className="btn btn-sm btn-primary" onClick={() => navigate('/document-extraction/review')}>
            <i className="bi bi-cloud-arrow-up me-1" />Upload Invoice
          </button>
        )}
      </div>

      {!importId && (
        <div className="dx-landing">
          <ProcessingQueuePanel
            tenantId={tenantId}
            storeId={storeId}
            actor={actor}
            disabled={!storeId}
            onOpenReview={(id) => { loadImports(); goToImport(id) }}
            registerOpenFilePicker={(open) => { openUploadPickerRef.current = open }}
          />

          {imports.length > 0 && (
            <div className="dx-landing__queue">
              <div className="dx-stat-row">
                <div className="dx-stat"><b>{pendingCount}</b><span>Needs Review</span></div>
                <div className="dx-stat dx-stat--warn"><b>{unknownSupplierCount}</b><span>Unknown Supplier</span></div>
                <div className="dx-stat dx-stat--danger"><b>{errorCount}</b><span>Has Errors</span></div>
              </div>
              <h6 className="dx-section-title">Recent Invoices</h6>
              <UniGrid
                columns={queueColumns}
                rows={imports}
                getRowId={(r) => String(r.import_id)}
                onRowClick={(r) => goToImport(r.import_id)}
                emptyTitle="No invoices yet"
              />
            </div>
          )}
        </div>
      )}

      {importId && error && <ErrorState description={error} onRetry={refresh} />}

      {importId && !error && (
        <div className="dx-workspace position-relative">
          {isLoading && <UniLoadingOverlay fullPage />}
          {review && (
            <>
              <div className="dx-workspace__viewer">
                <InvoiceViewer
                  importId={review.import_id}
                  pageCount={review.header.page_count}
                  hasPreview={Boolean(review.preview_image_path)}
                />
              </div>
              <div className="dx-workspace__main">
                <div className="dx-workspace__header">
                  <HeaderPanel
                    header={review.header}
                    items={review.items}
                    saving={isSaving}
                    onSaveHeader={async (patch) => {
                      setIsSaving(true)
                      try {
                        await documentExtractionService.updateHeader(review.import_id, { ...patch, actor })
                        await refresh()
                      } finally {
                        setIsSaving(false)
                      }
                    }}
                    onAssignSupplier={async (body) => {
                      setIsSaving(true)
                      try {
                        await documentExtractionService.assignSupplier(review.import_id, { ...body, actor })
                        await refresh()
                      } finally {
                        setIsSaving(false)
                      }
                    }}
                  />
                </div>
                <div className="dx-workspace__grid">
                  <InvoiceItemsGrid
                    items={review.items}
                    saving={isSaving}
                    onSaveItem={async (itemId, patch) => {
                      setIsSaving(true)
                      try {
                        await documentExtractionService.updateItem(review.import_id, itemId, { ...patch, actor })
                        await refresh()
                      } finally {
                        setIsSaving(false)
                      }
                    }}
                    onExcludeItem={async (itemId) => {
                      setIsSaving(true)
                      try {
                        await documentExtractionService.excludeItem(review.import_id, itemId, actor)
                        await refresh()
                      } finally {
                        setIsSaving(false)
                      }
                    }}
                  />
                </div>
                <div className="dx-workspace__valbar">
                  <ValidationPanel
                    status={review.status}
                    validationStatus={review.validation.validation_status}
                    findings={review.validation.findings}
                    saving={isSaving}
                    onComplete={handleComplete}
                    onDelete={handleDelete}
                  />
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  )
}
