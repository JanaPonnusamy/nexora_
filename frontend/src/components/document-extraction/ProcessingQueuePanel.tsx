import { useCallback, useEffect, useRef, useState } from 'react'
import {
  createJob, failedStage, jobOverallStatus, retryFailedStage, runPipeline,
  type PipelineJob, type StageState,
} from '../../services/documentExtractionPipeline'

interface ProcessingQueuePanelProps {
  tenantId: string
  storeId: string
  actor: string | null
  disabled?: boolean
  onOpenReview: (importId: number) => void
  /** Imperative handle so the workspace's Ctrl+U shortcut / "Upload" button
   *  can open the file picker without this component owning global focus. */
  registerOpenFilePicker?: (open: () => void) => void
}

const ACCEPT = '.pdf,.jpg,.jpeg,.png,.tif,.tiff,image/*,application/pdf'

function durationLabel(ms: number | null): string {
  if (ms == null) return ''
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

const STATUS_LABEL: Record<StageState['status'], string> = {
  pending: 'Waiting',
  running: 'Running',
  completed: 'Completed',
  failed: 'Failed',
  skipped: 'Skipped',
}

function StageIcon({ status }: { status: StageState['status'] }) {
  if (status === 'completed') return <i className="bi bi-check-circle-fill dx-stage__icon dx-stage__icon--ok" />
  if (status === 'failed') return <i className="bi bi-x-circle-fill dx-stage__icon dx-stage__icon--fail" />
  if (status === 'running') return <span className="spinner-border spinner-border-sm dx-stage__icon dx-stage__icon--run" role="status" aria-hidden="true" />
  if (status === 'skipped') return <i className="bi bi-dash-circle dx-stage__icon dx-stage__icon--skipped" />
  return <i className="bi bi-circle dx-stage__icon dx-stage__icon--pending" />
}

function StageRow({ stage }: { stage: StageState }) {
  const [showDetail, setShowDetail] = useState(false)
  // While running, "Elapsed Time" ticks live off startedAt; once the stage
  // settles it becomes the final "Duration" from durationMs. `now` is only
  // ever read from an effect (never Date.now() directly in render) to keep
  // the component pure.
  const [now, setNow] = useState(0)
  useEffect(() => {
    if (stage.status !== 'running') return
    const timer = setInterval(() => setNow(Date.now()), 500)
    return () => clearInterval(timer)
  }, [stage.status])
  const elapsedMs = stage.status === 'running' && stage.startedAt != null && now > 0 ? now - stage.startedAt : stage.durationMs

  return (
    <li className={`dx-stage dx-stage--${stage.status}${stage.warning ? ' dx-stage--warn' : ''}`}>
      <div className="dx-stage__row">
        <StageIcon status={stage.status} />
        <span className="dx-stage__label">{stage.label}</span>
        <span className="dx-stage__status">{STATUS_LABEL[stage.status]}</span>
        {stage.status === 'running' && (
          <span className="dx-stage__bar"><span className="dx-stage__bar-fill" style={{ width: `${stage.progressPct}%` }} /></span>
        )}
        {stage.note && stage.status !== 'failed' && <span className="dx-stage__note">{stage.note}</span>}
        {stage.status === 'failed' && (
          <span className="dx-stage__note dx-stage__note--fail">
            {stage.errorMessage}
            {stage.errorDetail && (
              <button type="button" className="dx-error-toggle" onClick={() => setShowDetail((v) => !v)}>
                {showDetail ? 'Hide details' : 'Details'}
              </button>
            )}
          </span>
        )}
        {stage.retryCount > 0 && (
          <span className="dx-stage__retry"><i className="bi bi-arrow-clockwise me-1" />Retry {stage.retryCount}</span>
        )}
        {elapsedMs != null && <span className="dx-stage__duration">{durationLabel(elapsedMs)}</span>}
      </div>
      {stage.status === 'failed' && showDetail && stage.errorDetail && (
        <div className="dx-error-detail">{stage.errorDetail}</div>
      )}
    </li>
  )
}

function JobCard({ job, onRetry, onOpenReview }: { job: PipelineJob; onRetry: (jobId: string) => void; onOpenReview: (importId: number) => void }) {
  const [showDetail, setShowDetail] = useState(false)
  const overall = jobOverallStatus(job)
  const failed = failedStage(job)
  const fileLabel = job.fileNames.length === 1 ? job.fileNames[0] : `${job.fileNames.length} files (1 invoice)`

  return (
    <div className={`dx-job dx-job--${overall}`}>
      <div className="dx-job__head">
        <i className="bi bi-file-earmark-text dx-job__file-icon" />
        <span className="dx-job__title">{job.invoiceNumber ? `Invoice #${job.invoiceNumber}` : fileLabel}</span>
        {job.importId != null && <span className="dx-job__id">#{job.importId}</span>}
        <span className="dx-job__spacer" />
        {overall === 'completed' && (
          <button type="button" className="btn btn-sm btn-primary" onClick={() => onOpenReview(job.importId!)}>
            Open Review <i className="bi bi-arrow-right ms-1" />
          </button>
        )}
        {overall === 'failed' && (
          <button type="button" className="btn btn-sm btn-outline-danger" onClick={() => onRetry(job.jobId)}>
            <i className="bi bi-arrow-clockwise me-1" />Retry
          </button>
        )}
      </div>

      <div className="dx-job__meta">
        <span className="dx-job__meta-item"><b>Invoice #</b>{job.invoiceNumber ?? '—'}</span>
        <span className="dx-job__meta-item"><b>Supplier</b>{job.supplierName ?? '—'}</span>
        <span className="dx-job__meta-item"><b>Page Count</b>{job.pageCount ?? '—'}</span>
        <span className="dx-job__meta-item"><b>Status</b>{STATUS_LABEL[overall]}</span>
      </div>

      {failed && (
        <div className="dx-job__error alert alert-danger py-1 px-2 mb-2">
          <b>{failed.label}</b> failed: {failed.errorMessage}
          {failed.errorDetail && (
            <button type="button" className="dx-error-toggle" onClick={() => setShowDetail((v) => !v)}>
              {showDetail ? 'Hide details' : 'Details'}
            </button>
          )}
          {showDetail && failed.errorDetail && <div className="dx-error-detail">{failed.errorDetail}</div>}
        </div>
      )}

      <ul className="dx-stage-list">
        {job.stages.map((s) => <StageRow key={s.id} stage={s} />)}
      </ul>
    </div>
  )
}

/** Upload dropzone plus a visible processing queue — every stage (Upload
 *  through Review Screen) is triggered automatically in order (see
 *  documentExtractionPipeline.ts) and
 *  reported live; a failed stage stops the chain and surfaces Stage/Reason/
 *  Retry instead of silently continuing or leaving a blank screen. */
export function ProcessingQueuePanel({ tenantId, storeId, actor, disabled, onOpenReview, registerOpenFilePicker }: ProcessingQueuePanelProps) {
  const [isDragOver, setIsDragOver] = useState(false)
  const [jobs, setJobs] = useState<PipelineJob[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)
  const cameraInputRef = useRef<HTMLInputElement>(null)
  const navigatedRef = useRef<Set<string>>(new Set())
  const jobsRef = useRef<PipelineJob[]>([])
  jobsRef.current = jobs

  const openFilePicker = useCallback(() => fileInputRef.current?.click(), [])

  useEffect(() => {
    registerOpenFilePicker?.(openFilePicker)
  }, [registerOpenFilePicker, openFilePicker])

  function updateJob(updated: PipelineJob) {
    setJobs((prev) => prev.map((j) => (j.jobId === updated.jobId ? updated : j)))
  }

  function startJob(files: File[]) {
    if (files.length === 0 || !tenantId || !storeId) return
    const job = createJob(files)
    setJobs((prev) => [...prev, job])
    void runPipeline(job, { tenantId, storeId, actor }, updateJob)
  }

  function retryJob(jobId: string) {
    const job = jobsRef.current.find((j) => j.jobId === jobId)
    if (!job) return
    void retryFailedStage(job, { tenantId, storeId, actor }, updateJob)
  }

  // Fast path: a lone invoice (the common case) still drops the operator
  // straight into Review the moment it's ready, matching the previous
  // single-upload flow. A batch of several in-flight jobs stays in the
  // queue instead — auto-navigating away would fight whichever job the
  // operator is currently watching.
  useEffect(() => {
    if (jobs.length !== 1) return
    const job = jobs[0]
    if (jobOverallStatus(job) === 'completed' && job.importId != null && !navigatedRef.current.has(job.jobId)) {
      navigatedRef.current.add(job.jobId)
      onOpenReview(job.importId)
    }
  }, [jobs, onOpenReview])

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? [])
    e.target.value = ''
    startJob(files)
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault()
    setIsDragOver(false)
    const files = Array.from(e.dataTransfer.files ?? [])
    startJob(files)
  }

  // Paste a screenshot / copied invoice image straight from the clipboard —
  // common on desktop when the invoice arrived in email or WhatsApp Web.
  useEffect(() => {
    if (disabled) return
    function onPaste(e: ClipboardEvent) {
      if (!tenantId || !storeId) return
      const items = Array.from(e.clipboardData?.items ?? [])
      const files = items
        .filter((it) => it.kind === 'file' && it.type.startsWith('image/'))
        .map((it) => it.getAsFile())
        .filter((f): f is File => f !== null)
      if (files.length > 0) startJob(files)
    }
    window.addEventListener('paste', onPaste)
    return () => window.removeEventListener('paste', onPaste)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [disabled, tenantId, storeId, actor])

  const activeJobs = [...jobs].reverse()

  return (
    <div className="dx-upload">
      <div
        className={`dx-upload__zone${isDragOver ? ' dx-upload__zone--drag' : ''}`}
        role="button"
        tabIndex={0}
        aria-label="Upload invoice"
        onClick={() => !disabled && openFilePicker()}
        onKeyDown={(e) => {
          if ((e.key === 'Enter' || e.key === ' ') && !disabled) {
            e.preventDefault()
            openFilePicker()
          }
        }}
        onDragOver={(e) => { e.preventDefault(); setIsDragOver(true) }}
        onDragLeave={() => setIsDragOver(false)}
        onDrop={handleDrop}
      >
        <i className="bi bi-cloud-arrow-up-fill dx-upload__icon" aria-hidden="true" />
        <div className="dx-upload__title">Drop an invoice here, or click to browse</div>
        <div className="dx-upload__hint">PDF, JPG, PNG, TIFF · or paste (Ctrl+V) a copied image · each drop processes automatically</div>
        <div className="dx-upload__actions" onClick={(e) => e.stopPropagation()}>
          <button type="button" className="btn btn-primary btn-sm" onClick={openFilePicker} disabled={disabled}>
            <i className="bi bi-folder2-open me-1" /> Browse Files
          </button>
          <button type="button" className="btn btn-outline-secondary btn-sm" onClick={() => cameraInputRef.current?.click()} disabled={disabled}>
            <i className="bi bi-camera-fill me-1" /> Use Camera
          </button>
        </div>
      </div>

      <input
        ref={fileInputRef} type="file" accept={ACCEPT} multiple hidden
        onChange={handleInputChange} disabled={disabled}
      />
      <input
        ref={cameraInputRef} type="file" accept="image/*" capture="environment" hidden
        onChange={handleInputChange} disabled={disabled}
      />

      {activeJobs.length > 0 && (
        <div className="dx-queue">
          <h6 className="dx-section-title">Processing Queue</h6>
          {activeJobs.map((job) => (
            <JobCard key={job.jobId} job={job} onRetry={retryJob} onOpenReview={onOpenReview} />
          ))}
        </div>
      )}
    </div>
  )
}
