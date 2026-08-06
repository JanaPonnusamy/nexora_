import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { EmptyState } from '../../components/common/EmptyState'
import { ErrorState } from '../../components/common/ErrorState'
import { PageHeader } from '../../components/common/PageHeader'
import { HeaderPanel } from '../../components/document-extraction/HeaderPanel'
import { InvoiceItemsGrid } from '../../components/document-extraction/InvoiceItemsGrid'
import { InvoiceViewer } from '../../components/document-extraction/InvoiceViewer'
import { ProcessingQueuePanel } from '../../components/document-extraction/ProcessingQueuePanel'
import { ValidationPanel } from '../../components/document-extraction/ValidationPanel'
import { statusLabel, STATUS_BADGE } from '../../components/document-extraction/statusLabels'
import '../../components/document-extraction/document-extraction.css'
import { AppDataGrid, type AppDataGridColumn } from '../../design-system/components/AppDataGrid'
import { InspectorPanel } from '../../design-system/components/InspectorPanel'
import { SplitView } from '../../design-system/components/SplitView'
import { KpiBar, StatCard } from '../../design-system/components/StatCard'
import { WorkspaceShell } from '../../design-system/components/WorkspaceShell'
import { useActingUser } from '../../hooks/useActingUser'
import { keyboardManager } from '../../platform/keyboard/KeyboardManager'
import { ApiError } from '../../services/apiClient'
import { documentExtractionService } from '../../services/documentExtractionService'
import { storeService } from '../../services/storeService'
import type { ImportListRow, ReviewPayload } from '../../types/documentExtraction'
import type { Store } from '../../types/store'

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
    storeService.list().then((all) => setStores(all.filter((store) => store.is_active))).catch(() => setStores([]))
  }, [])

  useEffect(() => {
    if (!storeId && stores.length > 0) setStoreId(stores[0].store_id)
  }, [stores, storeId])

  const tenantId = useMemo(
    () => stores.find((store) => store.store_id === storeId)?.tenant_id ?? '',
    [stores, storeId],
  )

  const loadImports = useCallback(() => {
    if (!tenantId) return
    documentExtractionService.listImports(tenantId, storeId)
      .then((page) => setImports(page.items))
      .catch(() => setImports([]))
  }, [tenantId, storeId])

  useEffect(() => {
    loadImports()
  }, [loadImports])

  const loadReview = useCallback(() => {
    if (!importId) {
      setReview(null)
      return
    }
    setIsLoading(true)
    setError(null)
    documentExtractionService.review(importId)
      .then(setReview)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load import'))
      .finally(() => setIsLoading(false))
  }, [importId])

  useEffect(() => {
    loadReview()
  }, [loadReview])

  async function refresh() {
    loadReview()
    loadImports()
  }

  const queueIndex = importId ? imports.findIndex((row) => String(row.import_id) === importId) : -1

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

  function goToNextPending(afterId: number) {
    const startIdx = imports.findIndex((row) => row.import_id === afterId)
    const ordered = imports.filter((row) => row.import_id !== afterId)
    const rotated = startIdx >= 0 ? [...imports.slice(startIdx + 1), ...imports.slice(0, startIdx)] : ordered
    const next = rotated.find((row) => row.status !== 'SAVED' && row.status !== 'EXPORTED')
    if (next) navigate(`/document-extraction/review/${next.import_id}`)
    else navigate('/document-extraction/review')
  }

  async function handleComplete() {
    if (!review) return
    setIsSaving(true)
    try {
      try {
        await documentExtractionService.save(review.import_id, false, actor)
      } catch (err) {
        if (err instanceof ApiError && err.status === 409) {
          const proceed = window.confirm('This invoice still has unresolved validation errors. Save it anyway?')
          if (!proceed) return
          await documentExtractionService.save(review.import_id, true, actor)
        } else {
          throw err
        }
      }
      const savedId = review.import_id
      await refresh()
      goToNextPending(savedId)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed')
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
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed')
    } finally {
      setIsSaving(false)
    }
  }

  useEffect(() => {
    const unregisterSave = keyboardManager.register('ctrl+s', (event) => {
      event.preventDefault()
      if (review) void handleComplete()
    })
    const unregisterUpload = keyboardManager.register('ctrl+u', (event) => {
      event.preventDefault()
      if (importId) navigate('/document-extraction/review')
      else openUploadPickerRef.current?.()
    })
    const unregisterNext = keyboardManager.register('pagedown', (event) => {
      if (isTextEditor(document.activeElement)) return
      event.preventDefault()
      goRelative(1)
    })
    const unregisterPrev = keyboardManager.register('pageup', (event) => {
      if (isTextEditor(document.activeElement)) return
      event.preventDefault()
      goRelative(-1)
    })
    return () => {
      unregisterSave()
      unregisterUpload()
      unregisterNext()
      unregisterPrev()
    }
  })

  const queueColumns: AppDataGridColumn<ImportListRow>[] = [
    { key: 'invoice_number', header: 'Invoice #', render: (row) => row.invoice_number ?? '-' },
    {
      key: 'supplier_name',
      header: 'Supplier',
      render: (row) => (
        <div className="d-flex align-items-center gap-2">
          <span>{row.supplier_name ?? '-'}</span>
          {row.is_supplier_unknown && <span className="badge text-bg-danger">Unknown</span>}
        </div>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      render: (row) => <span className={`badge ${STATUS_BADGE[row.status] ?? 'text-bg-secondary'}`}>{statusLabel(row.status)}</span>,
    },
    {
      key: 'validation_status',
      header: 'Validation',
      render: (row) => (
        <span className={`badge ${row.validation_status === 'FAILED' ? 'text-bg-danger' : row.validation_status === 'WARNING' ? 'text-bg-warning' : 'text-bg-secondary'}`}>
          {row.validation_status === 'FAILED' ? 'Errors' : row.validation_status === 'WARNING' ? 'Warnings' : row.validation_status}
        </span>
      ),
    },
    {
      key: 'net_amount',
      header: 'Net Amount',
      align: 'end',
      render: (row) => (row.net_amount != null ? `Rs. ${row.net_amount.toLocaleString('en-IN')}` : '-'),
    },
    {
      key: 'uploaded_at',
      header: 'Uploaded',
      render: (row) => new Date(row.uploaded_at).toLocaleString(),
    },
  ]

  const pendingCount = imports.filter((row) => row.status !== 'SAVED' && row.status !== 'EXPORTED').length
  const unknownSupplierCount = imports.filter((row) => row.is_supplier_unknown).length
  const errorCount = imports.filter((row) => row.validation_status === 'FAILED').length

  const header = (
    <div className="d-flex flex-column gap-3">
      <PageHeader
        title="Document Extraction Review"
        breadcrumb={['Operations', 'Document Extraction', 'Review']}
        description="Review OCR imports, correct mappings, validate invoice lines, and move the queue forward without changing the extraction workflow."
      />
      <div className="ds-toolbar">
        <label className="d-flex flex-column gap-1">
          <span className="small text-muted">Store</span>
          <select className="form-select" value={storeId} onChange={(event) => setStoreId(event.target.value)}>
            {stores.map((store) => (
              <option key={store.store_id} value={store.store_id}>
                {store.store_code} - {store.store_name}
              </option>
            ))}
          </select>
        </label>
        {importId && (
          <>
            <label className="d-flex flex-column gap-1 flex-grow-1">
              <span className="small text-muted">Jump to invoice</span>
              <select
                className="form-select"
                value={importId}
                onChange={(event) => goToImport(Number(event.target.value))}
              >
                <option value="">Jump to invoice</option>
                {imports.map((row) => (
                  <option key={row.import_id} value={row.import_id}>
                    #{row.import_id} - {row.invoice_number ?? 'No invoice'} - {row.supplier_name ?? 'Unknown supplier'}
                  </option>
                ))}
              </select>
            </label>
            <div className="d-flex align-items-end gap-2">
              <button
                type="button"
                className="btn btn-outline-secondary ds-button"
                disabled={queueIndex <= 0}
                onClick={() => goRelative(-1)}
                title="Previous invoice (Page Up)"
              >
                <i className="bi bi-chevron-left" aria-hidden="true" />
              </button>
              <button
                type="button"
                className="btn btn-outline-secondary ds-button"
                disabled={queueIndex < 0 || queueIndex >= imports.length - 1}
                onClick={() => goRelative(1)}
                title="Next invoice (Page Down)"
              >
                <i className="bi bi-chevron-right" aria-hidden="true" />
              </button>
              <button
                type="button"
                className="btn btn-primary ds-button ds-button--primary"
                onClick={() => navigate('/document-extraction/review')}
              >
                <i className="bi bi-cloud-arrow-up me-1" aria-hidden="true" />
                Upload Invoice
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )

  const kpis = !importId ? (
    <KpiBar>
      <StatCard label="Needs Review" value={pendingCount.toLocaleString()} icon="bi-hourglass-split" tone="primary" />
      <StatCard label="Unknown Supplier" value={unknownSupplierCount.toLocaleString()} icon="bi-exclamation-triangle" tone="warning" />
      <StatCard label="Has Errors" value={errorCount.toLocaleString()} icon="bi-x-octagon" tone="danger" />
      <StatCard label="Queue Size" value={imports.length.toLocaleString()} icon="bi-card-checklist" />
    </KpiBar>
  ) : undefined

  const statusBar = importId && review ? (
    <div className="d-flex flex-wrap align-items-center gap-3">
      <span className={`badge ${STATUS_BADGE[review.status] ?? 'text-bg-secondary'}`}>{statusLabel(review.status)}</span>
      <span className={`badge ${review.validation.validation_status === 'FAILED' ? 'text-bg-danger' : review.validation.validation_status === 'WARNING' ? 'text-bg-warning' : 'text-bg-secondary'}`}>
        {review.validation.validation_status}
      </span>
      <span className="text-muted">Ctrl+S to save, Ctrl+U to upload, Page Up / Page Down to move through the queue.</span>
    </div>
  ) : undefined

  const landingContent = (
    <div className="d-flex flex-column gap-4">
      <ProcessingQueuePanel
        tenantId={tenantId}
        storeId={storeId}
        actor={actor}
        disabled={!storeId}
        onOpenReview={(id) => {
          loadImports()
          goToImport(id)
        }}
        registerOpenFilePicker={(open) => {
          openUploadPickerRef.current = open
        }}
      />

      <AppDataGrid
        title="Recent Invoices"
        storageKey="document-extraction-review-queue"
        columns={queueColumns}
        rows={imports}
        getRowId={(row) => String(row.import_id)}
        onRowClick={(row) => goToImport(row.import_id)}
        emptyTitle="No invoices yet"
        emptyDescription="Imports will appear here after invoices are uploaded for the selected store."
        pageSize={10}
      />
    </div>
  )

  const reviewWorkspace = error ? (
    <ErrorState description={error} onRetry={refresh} />
  ) : isLoading && !review ? (
    <InspectorPanel
      title="Loading review"
      summary="Fetching OCR output, mapped header fields, invoice items, and validation state."
      empty
      emptyTitle="Preparing invoice workspace"
      emptyDescription="The review workspace will appear as soon as the selected invoice finishes loading."
    />
  ) : review ? (
    <SplitView
      primary={
        <InvoiceViewer
          importId={review.import_id}
          pageCount={review.header.page_count}
          hasPreview={Boolean(review.preview_image_path)}
        />
      }
      secondary={
        <div className="d-flex flex-column gap-3">
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
      }
      tertiary={
        <InspectorPanel
          title="Validation"
          summary={`${review.items.length.toLocaleString()} invoice lines in scope`}
        >
          <ValidationPanel
            status={review.status}
            validationStatus={review.validation.validation_status}
            findings={review.validation.findings}
            saving={isSaving}
            onComplete={handleComplete}
            onDelete={handleDelete}
          />
        </InspectorPanel>
      }
      primaryDefault={40}
      secondaryDefault={36}
      tertiaryDefault={24}
    />
  ) : (
    <EmptyState
      icon="bi-file-earmark-medical"
      title="Pick an invoice to review"
      description="Choose an import from the queue or upload a new file to open the review workspace."
    />
  )

  return (
    <WorkspaceShell header={header} kpis={kpis} statusBar={statusBar} fullWidth>
      {!importId ? landingContent : reviewWorkspace}
    </WorkspaceShell>
  )
}
