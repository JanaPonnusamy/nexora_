import type { DocImportItem, DocImportRow } from '../../types/documentExtraction'

/** The 5 highlight conditions named in the module brief: Missing Product,
 *  Unknown Supplier, Low Confidence, Invalid Batch, Invalid Expiry. Pure
 *  functions so both the grid (row styling) and the edit panel (field-level
 *  warnings) share one definition of "wrong" instead of drifting apart. */

export const LOW_CONFIDENCE_THRESHOLD = 0.6

export function isLowConfidence(score: number | null | undefined): boolean {
  return score != null && score < LOW_CONFIDENCE_THRESHOLD
}

export function isMissingProduct(item: DocImportItem): boolean {
  return !item.product_code
}

// A real batch number is alphanumeric and at least 2 characters — OCR
// noise ("--", ".", a single stray character) is the common failure mode,
// not a wrong-but-plausible value.
export function isInvalidBatch(item: DocImportItem): boolean {
  const batch = (item.batch_number ?? '').trim()
  return batch.length < 2 || !/[A-Za-z0-9]/.test(batch)
}

export function isInvalidExpiry(item: DocImportItem): boolean {
  if (item.expiry_date) {
    // Expired stock reaching an invoice is unusual enough to flag for a
    // human look, not auto-reject.
    return new Date(item.expiry_date).getTime() < Date.now()
  }
  // expiry_raw present but never resolved to a real date = OCR couldn't
  // parse it (e.g. "13/25" isn't a valid month/year).
  return Boolean(item.expiry_raw)
}

export function itemHighlights(item: DocImportItem): string[] {
  const flags: string[] = []
  if (isMissingProduct(item)) flags.push('Missing Product')
  if (isLowConfidence(item.confidence)) flags.push('Low Confidence')
  if (isInvalidBatch(item)) flags.push('Invalid Batch')
  if (isInvalidExpiry(item)) flags.push('Invalid Expiry')
  return flags
}

export function headerHighlights(header: DocImportRow): string[] {
  const flags: string[] = []
  if (header.is_supplier_unknown) flags.push('Unknown Supplier')
  if (isLowConfidence(header.supplier_match_confidence)) flags.push('Low Confidence Supplier Match')
  return flags
}

/** Money comparisons are never exact after OCR/rounding — anything within
 *  this many rupees of zero counts as "balanced" rather than a mismatch. */
const RECONCILE_TOLERANCE = 1

export interface ReconcileCheck {
  label: string
  extracted: number | null
  computed: number
  balanced: boolean
}

/** Sums the (non-excluded) product lines and compares each total against the
 *  header's own extracted figure — the "does this invoice add up" check an
 *  operator needs before trusting it, independent of the per-field
 *  validation findings the backend already returns. */
export function reconcileTotals(header: DocImportRow, items: DocImportItem[]): ReconcileCheck[] {
  const live = items.filter((i) => !i.is_excluded)
  const sum = (pick: (i: DocImportItem) => number | null) =>
    live.reduce((acc, i) => acc + (pick(i) ?? 0), 0)

  const computedAmount = sum((i) => i.amount)
  const computedQty = sum((i) => i.quantity)

  const checks: ReconcileCheck[] = [
    {
      label: 'Net Amount vs. Line Items',
      extracted: header.net_amount,
      computed: computedAmount,
      balanced: header.net_amount == null || Math.abs(header.net_amount - computedAmount) <= RECONCILE_TOLERANCE,
    },
    {
      label: 'Total Qty vs. Line Items',
      extracted: header.total_quantity,
      computed: computedQty,
      balanced: header.total_quantity == null || Math.abs(header.total_quantity - computedQty) <= RECONCILE_TOLERANCE,
    },
    {
      label: 'Item Count vs. Line Items',
      extracted: header.item_count,
      computed: live.length,
      balanced: header.item_count == null || header.item_count === live.length,
    },
  ]
  return checks
}
