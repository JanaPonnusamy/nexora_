/** Automatic processing pipeline for Document Extraction (frontend/service
 *  layer orchestration only — the backend endpoints it calls are untouched
 *  aside from one thin route, POST .../preprocess, that exposes the
 *  already-existing service.run_image_processing so Image Processing can be
 *  its own reportable/retryable stage like the rest).
 *
 *  The 9 stages the operator sees are not a 1:1 map to network calls: the
 *  backend's single POST .../extract runs Header Extraction, Product Table
 *  Understanding, Supplier Detection and Product Resolution together as one
 *  atomic, all-or-nothing call (see service.run_extraction) — there is no
 *  way to observe or retry them individually without changing the backend,
 *  which is out of scope here. Those four stages are driven in lockstep by
 *  that one call and enriched afterward from GET .../review so their
 *  "Completed" notes still reflect real results (item counts, supplier
 *  match, product-resolution rate) rather than being purely cosmetic.
 */
import { documentExtractionService } from './documentExtractionService'
import type { DocImportRow, ReviewPayload } from '../types/documentExtraction'

export type PipelineStageId =
  | 'upload'
  | 'image_processing'
  | 'ocr'
  | 'header_extraction'
  | 'table_understanding'
  | 'supplier_detection'
  | 'product_resolution'
  | 'financial_validation'
  | 'review'

export type StageStatus = 'pending' | 'running' | 'completed' | 'failed' | 'skipped'

export interface StageState {
  id: PipelineStageId
  label: string
  status: StageStatus
  progressPct: number
  startedAt: number | null
  durationMs: number | null
  note: string | null
  warning: boolean
  /** Short, operator-facing summary (e.g. "OCR Service Unavailable"). */
  errorMessage: string | null
  /** Raw exception/detail text (e.g. "ModuleNotFoundError: No module named
   *  'paddleocr'"), only ever shown behind an explicit "Details" toggle. */
  errorDetail: string | null
  retryCount: number
}

export interface PipelineJob {
  jobId: string
  fileNames: string[]
  files: File[]
  importId: number | null
  stages: StageState[]
  createdAt: number
  invoiceNumber: string | null
  supplierName: string | null
  pageCount: number | null
}

export interface PipelineContext {
  tenantId: string
  storeId: string
  actor: string | null
}

type Group = 'upload' | 'image_processing' | 'ocr' | 'extract' | 'validation' | 'review'

const GROUP_ORDER: Group[] = ['upload', 'image_processing', 'ocr', 'extract', 'validation', 'review']

const STAGE_DEFS: { id: PipelineStageId; label: string; group: Group }[] = [
  { id: 'upload', label: 'Upload', group: 'upload' },
  { id: 'image_processing', label: 'Image Processing', group: 'image_processing' },
  { id: 'ocr', label: 'OCR', group: 'ocr' },
  { id: 'header_extraction', label: 'Header Extraction', group: 'extract' },
  { id: 'table_understanding', label: 'Product Table Understanding', group: 'extract' },
  { id: 'supplier_detection', label: 'Supplier Detection', group: 'extract' },
  { id: 'product_resolution', label: 'Product Resolution', group: 'extract' },
  { id: 'financial_validation', label: 'Financial Validation', group: 'validation' },
  { id: 'review', label: 'Review Screen', group: 'review' },
]

const GROUP_OF: Record<PipelineStageId, Group> = STAGE_DEFS.reduce(
  (acc, d) => ({ ...acc, [d.id]: d.group }),
  {} as Record<PipelineStageId, Group>,
)

export function createJob(files: File[]): PipelineJob {
  return {
    jobId: typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `job-${Date.now()}-${Math.random()}`,
    fileNames: files.map((f) => f.name),
    files,
    importId: null,
    createdAt: Date.now(),
    invoiceNumber: null,
    supplierName: null,
    pageCount: null,
    stages: STAGE_DEFS.map((d) => ({
      id: d.id,
      label: d.label,
      status: 'pending',
      progressPct: 0,
      startedAt: null,
      durationMs: null,
      note: null,
      warning: false,
      errorMessage: null,
      errorDetail: null,
      retryCount: 0,
    })),
  }
}

export function jobOverallStatus(job: PipelineJob): StageStatus {
  if (job.stages.some((s) => s.status === 'failed')) return 'failed'
  if (job.stages.every((s) => s.status === 'completed')) return 'completed'
  if (job.stages.some((s) => s.status === 'running')) return 'running'
  return 'pending'
}

export function failedStage(job: PipelineJob): StageState | null {
  return job.stages.find((s) => s.status === 'failed') ?? null
}

function cloneJob(job: PipelineJob): PipelineJob {
  return { ...job, stages: job.stages.map((s) => ({ ...s })) }
}

function setStages(job: PipelineJob, ids: PipelineStageId[], patch: Partial<StageState> | ((s: StageState) => Partial<StageState>)) {
  job.stages = job.stages.map((s) =>
    ids.includes(s.id) ? { ...s, ...(typeof patch === 'function' ? patch(s) : patch) } : s,
  )
}

function tickProgress(job: PipelineJob, ids: PipelineStageId[], emit: (job: PipelineJob) => void): () => void {
  const timer = setInterval(() => {
    setStages(job, ids, (s) => (s.status === 'running' ? { progressPct: Math.min(92, s.progressPct + Math.random() * 10 + 3) } : {}))
    emit(cloneJob(job))
  }, 350)
  return () => clearInterval(timer)
}

interface StageOutcome {
  ok: boolean
  note?: string
  warning?: boolean
  error?: string
}

/** Translates a raw backend/network error string into a short, operator-facing
 *  message. The raw string is never discarded — it's always kept as
 *  errorDetail for the "Details" toggle — this only decides what's shown by
 *  default so operators aren't shown stack-trace-flavored text like
 *  "ModuleNotFoundError: No module named 'paddleocr'". */
const USER_MESSAGE_RULES: { test: RegExp; message: string }[] = [
  { test: /paddleocr|ModuleNotFoundError|No module named/i, message: 'OCR Service Unavailable' },
  { test: /no (processed or )?original page images|image processing failed/i, message: 'Could Not Process Image' },
  { test: /unable to reach the server/i, message: 'Server Unreachable' },
  { test: /timed out/i, message: 'Request Timed Out' },
  { test: /extraction failed/i, message: 'Could Not Extract Invoice Data' },
  { test: /supplier/i, message: 'Supplier Identification Failed' },
]

function classifyError(raw: string): { userMessage: string; devDetail: string } {
  const rule = USER_MESSAGE_RULES.find((r) => r.test.test(raw))
  return { userMessage: rule?.message ?? 'Processing Failed', devDetail: raw }
}

/** Runs one network call and drives every stage id in `ids` through it in
 *  lockstep (a group of >1 id only happens for the 4 stages bundled inside
 *  POST .../extract, per the module docstring above). */
async function runOne(
  job: PipelineJob,
  ids: PipelineStageId[],
  emit: (job: PipelineJob) => void,
  call: () => Promise<DocImportRow>,
  evaluate: (doc: DocImportRow) => StageOutcome,
): Promise<boolean> {
  const startedAt = Date.now()
  setStages(job, ids, { status: 'running', startedAt, progressPct: 8, durationMs: null, errorMessage: null })
  emit(cloneJob(job))
  const stopTicker = tickProgress(job, ids, emit)

  let outcome: StageOutcome
  let doc: DocImportRow | null = null
  try {
    doc = await call()
    outcome = evaluate(doc)
  } catch (e) {
    outcome = { ok: false, error: e instanceof Error ? e.message : 'Request failed' }
  }
  stopTicker()

  if (doc?.import_id) job.importId = doc.import_id
  if (doc?.invoice_number) job.invoiceNumber = doc.invoice_number
  if (doc?.supplier_name) job.supplierName = doc.supplier_name
  if (doc?.page_count != null) job.pageCount = doc.page_count

  const durationMs = Date.now() - startedAt
  if (outcome.ok) {
    setStages(job, ids, { status: 'completed', progressPct: 100, durationMs, note: outcome.note ?? null, warning: !!outcome.warning })
  } else {
    const { userMessage, devDetail } = classifyError(outcome.error ?? doc?.failure_reason ?? 'Stage failed')
    setStages(job, ids, {
      status: 'failed',
      progressPct: 100,
      durationMs,
      errorMessage: userMessage,
      errorDetail: devDetail,
    })
  }
  emit(cloneJob(job))
  return outcome.ok
}

function annotateExtractSubStages(job: PipelineJob, review: ReviewPayload) {
  const header = review.header
  const items = review.items
  const resolved = items.filter((it) => it.product_code).length

  setStages(job, ['header_extraction'], {
    note: header.invoice_number ? `Invoice ${header.invoice_number}` : 'Header parsed',
    warning: !header.invoice_number || header.net_amount == null,
  })
  setStages(job, ['table_understanding'], {
    note: `${items.length} line item${items.length === 1 ? '' : 's'}`,
    warning: items.length === 0,
  })
  setStages(job, ['supplier_detection'], {
    note: header.is_supplier_unknown ? 'Supplier unknown' : (header.supplier_name ?? 'Matched'),
    warning: header.is_supplier_unknown,
  })
  setStages(job, ['product_resolution'], {
    note: `${resolved}/${items.length} product(s) matched`,
    warning: resolved < items.length,
  })
}

async function runGroup(job: PipelineJob, group: Group, ctx: PipelineContext, emit: (job: PipelineJob) => void): Promise<boolean> {
  switch (group) {
    case 'upload':
      return runOne(
        job, ['upload'], emit,
        async () => {
          const { imports } = await documentExtractionService.uploadFiles(job.files, ctx.tenantId, ctx.storeId, ctx.actor)
          return imports[0]
        },
        () => ({ ok: true, note: `${job.files.length} file${job.files.length === 1 ? '' : 's'} received` }),
      )

    case 'image_processing':
      return runOne(
        job, ['image_processing'], emit,
        () => documentExtractionService.runPreprocess(job.importId!, ctx.actor),
        (doc) => doc.is_image_processed
          ? { ok: true, note: doc.page_count ? `${doc.page_count} page(s) enhanced` : 'Pages enhanced' }
          : { ok: false, error: doc.failure_reason ?? 'Image processing failed' },
      )

    case 'ocr':
      return runOne(
        job, ['ocr'], emit,
        () => documentExtractionService.runOcr(job.importId!, ctx.actor),
        (doc) => {
          if (!doc.is_ocr_completed) return { ok: false, error: doc.failure_reason ?? 'OCR failed' }
          const splitCount = doc.split_import_ids?.length ?? 0
          const confidence = doc.ocr_confidence != null ? `${doc.ocr_confidence}% confidence` : 'Text recognized'
          if (splitCount === 0) return { ok: true, note: confidence }
          // The upload held more than one invoice. This job keeps following
          // the first one; the others are already extracted and waiting in
          // History, so the note has to say so — otherwise the operator sees
          // one invoice come out of a four-page upload and assumes the rest
          // was lost.
          return {
            ok: true,
            warning: true,
            note: `${confidence} — ${splitCount + 1} invoices found; ${splitCount} split into separate import(s), see History`,
          }
        },
      )

    case 'extract': {
      const ids: PipelineStageId[] = ['header_extraction', 'table_understanding', 'supplier_detection', 'product_resolution']
      const ok = await runOne(
        job, ids, emit,
        () => documentExtractionService.runExtract(job.importId!, ctx.actor),
        (doc) => (doc.is_header_extracted && doc.is_items_extracted)
          ? { ok: true }
          : { ok: false, error: doc.failure_reason ?? 'Extraction failed' },
      )
      if (!ok) return false
      try {
        const review = await documentExtractionService.review(job.importId!)
        annotateExtractSubStages(job, review)
        emit(cloneJob(job))
      } catch {
        // Enrichment is best-effort only (a second, read-only fetch) — the
        // stages above are already marked completed; a failed fetch here
        // must not fail a stage that has already genuinely succeeded.
      }
      return true
    }

    case 'validation':
      return runOne(
        job, ['financial_validation'], emit,
        () => documentExtractionService.runValidate(job.importId!, ctx.actor),
        (doc) => ({
          ok: true,
          warning: doc.validation_status !== 'PASSED',
          note: doc.validation_status === 'PASSED'
            ? 'No issues found'
            : doc.validation_status === 'WARNING'
              ? 'Needs attention in Review'
              : 'Has errors — needs Review',
        }),
      )

    case 'review': {
      const startedAt = Date.now()
      setStages(job, ['review'], { status: 'completed', progressPct: 100, startedAt, durationMs: 0, note: 'Ready for review' })
      emit(cloneJob(job))
      return true
    }
  }
}

/** Runs every remaining stage from `fromGroup` onward, stopping immediately
 *  (leaving later stages 'pending') the first time a stage fails — the
 *  operator never sees a later stage attempted against data an earlier one
 *  failed to produce. */
export async function runPipeline(
  job: PipelineJob,
  ctx: PipelineContext,
  emit: (job: PipelineJob) => void,
  fromGroup: Group = 'upload',
): Promise<void> {
  const startIdx = GROUP_ORDER.indexOf(fromGroup)
  for (let i = startIdx; i < GROUP_ORDER.length; i++) {
    const ok = await runGroup(job, GROUP_ORDER[i], ctx, emit)
    if (!ok) {
      // A failed stage stops the chain — every stage in a later group was
      // never attempted and never will be until a retry, so it's marked
      // 'skipped' rather than left looking like it's still 'Waiting'.
      const laterGroups = new Set(GROUP_ORDER.slice(i + 1))
      job.stages = job.stages.map((s) =>
        s.status === 'pending' && laterGroups.has(GROUP_OF[s.id]) ? { ...s, status: 'skipped' } : s,
      )
      emit(cloneJob(job))
      return
    }
  }
}

/** Re-runs just the stage that failed (and everything after it, same as the
 *  first pass) — the group that stage belongs to is re-attempted from
 *  scratch since the backend call it maps to is atomic. */
export async function retryFailedStage(job: PipelineJob, ctx: PipelineContext, emit: (job: PipelineJob) => void): Promise<void> {
  const failed = failedStage(job)
  if (!failed) return
  const group = GROUP_OF[failed.id]
  const idsInGroup = STAGE_DEFS.filter((d) => d.group === group).map((d) => d.id)
  setStages(job, idsInGroup, (s) => ({ retryCount: s.retryCount + 1 }))
  emit(cloneJob(job))
  await runPipeline(job, ctx, emit, group)
}
