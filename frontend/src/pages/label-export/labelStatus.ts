/**
 * Explicit workflow state model for the Label Exporter review grid (spec §20).
 *
 * The backend stores the raw facts on dbo.label_review — include_label (NULL/Y/N),
 * unit_description / old_unit_description (unit correction), assigned_sublocation
 * (the box the engine placed the product in) and label_required. These helpers
 * derive the THREE separate, non-overlapping status axes the UI shows so that
 * "pending", "excluded", etc. mean exactly one thing everywhere.
 */

import type { LabelSearchRow } from '../../types/labelExporter'

/* Review: the reviewer's include/exclude decision. */
export const ReviewStatus = {
  NOT_REVIEWED: 'NOT_REVIEWED',
  INCLUDED: 'INCLUDED',
  EXCLUDED: 'EXCLUDED',
} as const
export type ReviewStatus = (typeof ReviewStatus)[keyof typeof ReviewStatus]

/* Assignment: whether the product has a shelf box yet. Separate from review. */
export const AssignmentStatus = {
  NOT_STARTED: 'NOT_STARTED', // review not done
  NOT_REQUIRED: 'NOT_REQUIRED', // excluded
  PENDING: 'PENDING', // included, no location yet
  ASSIGNED: 'ASSIGNED', // included, location assigned
} as const
export type AssignmentStatus = (typeof AssignmentStatus)[keyof typeof AssignmentStatus]

/* Label: print lifecycle. Kept separate from location assignment. */
export const LabelStatus = {
  NOT_REQUIRED: 'NOT_REQUIRED',
  READY: 'READY',
  PRINTED: 'PRINTED',
} as const
export type LabelStatus = (typeof LabelStatus)[keyof typeof LabelStatus]

function clean(value: string | null | undefined): string {
  return (value ?? '').trim()
}

/** Raw DB value 'Y' / 'N' / null → ReviewStatus enum. */
export function deriveReview(row: LabelSearchRow): ReviewStatus {
  if (row.include_label === 'Y') return ReviewStatus.INCLUDED
  if (row.include_label === 'N') return ReviewStatus.EXCLUDED
  return ReviewStatus.NOT_REVIEWED
}

export function hasAssignedLocation(row: LabelSearchRow): boolean {
  return clean(row.assigned_sublocation) !== ''
}

export function deriveAssignment(row: LabelSearchRow): AssignmentStatus {
  const review = deriveReview(row)
  if (review === ReviewStatus.NOT_REVIEWED) return AssignmentStatus.NOT_STARTED
  if (review === ReviewStatus.EXCLUDED) return AssignmentStatus.NOT_REQUIRED
  return hasAssignedLocation(row) ? AssignmentStatus.ASSIGNED : AssignmentStatus.PENDING
}

/**
 * Label status for the grid. The search row does not carry label_created_at
 * (that lives in the label queue), so from the review grid an assigned product
 * is READY; the queue view resolves READY→PRINTED once a sheet is exported.
 */
export function deriveLabel(row: LabelSearchRow): LabelStatus {
  return deriveAssignment(row) === AssignmentStatus.ASSIGNED ? LabelStatus.READY : LabelStatus.NOT_REQUIRED
}

/* ---------- Unit correction (spec §1/§2) ---------- */

/** The historical unit that is never overwritten. */
export function oldUnitOf(row: LabelSearchRow): string {
  return clean(row.old_unit_description) || clean(row.unit_description)
}

/** The current/corrected unit used for ALL downstream logic. */
export function currentUnitOf(row: LabelSearchRow): string {
  return clean(row.corrected_unit) || clean(row.unit_description)
}

export function isUnitCorrected(row: LabelSearchRow): boolean {
  const corrected = clean(row.corrected_unit)
  return corrected !== '' && corrected.toUpperCase() !== oldUnitOf(row).toUpperCase()
}

/* ---------- Location (spec §6/§7) ---------- */

export function newLocationOf(row: LabelSearchRow): string {
  return clean(row.assigned_sublocation)
}

export function oldLocationOf(row: LabelSearchRow): string {
  return clean(row.old_sublocation) || clean(row.current_sublocation)
}

/* ---------- Badge presentation ---------- */

export interface StatusBadge {
  label: string
  className: string
  glyph: string
}

export function assignmentBadge(status: AssignmentStatus): StatusBadge {
  switch (status) {
    case AssignmentStatus.ASSIGNED:
      return { label: 'Assigned', className: 'lx-badge--assigned', glyph: '✓' }
    case AssignmentStatus.PENDING:
      return { label: 'Pending', className: 'lx-badge--pending', glyph: '●' }
    case AssignmentStatus.NOT_REQUIRED:
      return { label: 'Excluded', className: 'lx-badge--excluded', glyph: '—' }
    default:
      return { label: 'Not reviewed', className: 'lx-badge--neutral', glyph: '·' }
  }
}

/* ---------- Aggregate counters (spec §11) ---------- */

export interface ReviewCounters {
  total: number
  reviewed: number
  included: number
  excluded: number
  remaining: number
  locationPending: number
  assigned: number
}

export function computeCounters(rows: LabelSearchRow[]): ReviewCounters {
  const c: ReviewCounters = {
    total: rows.length,
    reviewed: 0,
    included: 0,
    excluded: 0,
    remaining: 0,
    locationPending: 0,
    assigned: 0,
  }
  for (const row of rows) {
    const review = deriveReview(row)
    if (review === ReviewStatus.NOT_REVIEWED) {
      c.remaining += 1
      continue
    }
    c.reviewed += 1
    if (review === ReviewStatus.EXCLUDED) {
      c.excluded += 1
      continue
    }
    c.included += 1
    if (deriveAssignment(row) === AssignmentStatus.ASSIGNED) c.assigned += 1
    else c.locationPending += 1
  }
  return c
}

/** Products eligible for the Assign Locations action (spec §12): Review=Y AND Pending. */
export function isAssignable(row: LabelSearchRow): boolean {
  return deriveAssignment(row) === AssignmentStatus.PENDING
}
