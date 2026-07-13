/** Operator-facing copy for the backend's pipeline-stage status codes — the
 *  Review workspace should read like a task list ("Ready to Save"), not
 *  expose the underlying state-machine names. */
export const STATUS_LABEL: Record<string, string> = {
  UPLOADED: 'Processing…',
  PROCESSING: 'Processing…',
  EXTRACTED: 'Needs Review',
  REVIEW_PENDING: 'Needs Review',
  SAVED: 'Saved',
  EXPORTED: 'Exported',
  FAILED: 'Processing Failed',
}

export function statusLabel(status: string): string {
  return STATUS_LABEL[status] ?? status
}

export const VALIDATION_LABEL: Record<string, string> = {
  PASSED: 'No Issues',
  WARNING: 'Needs Attention',
  FAILED: 'Has Errors',
  PENDING: 'Not Checked Yet',
}

export function validationLabel(status: string): string {
  return VALIDATION_LABEL[status] ?? status
}

export const VALIDATION_BADGE: Record<string, string> = {
  PASSED: 'text-bg-success',
  WARNING: 'text-bg-warning',
  FAILED: 'text-bg-danger',
  PENDING: 'text-bg-secondary',
}

export const STATUS_BADGE: Record<string, string> = {
  UPLOADED: 'text-bg-secondary',
  PROCESSING: 'text-bg-secondary',
  EXTRACTED: 'text-bg-warning',
  REVIEW_PENDING: 'text-bg-warning',
  SAVED: 'text-bg-success',
  EXPORTED: 'text-bg-primary',
  FAILED: 'text-bg-danger',
}
