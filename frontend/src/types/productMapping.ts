export type MappingStatus = 'AUTO' | 'PENDING' | 'APPROVED' | 'REJECTED'
export type MatchMethod =
  | 'SUPPLIER' | 'EXACT' | 'NORMALIZED' | 'STRUCTURED' | 'FUZZY' | 'MANUAL' | null

export interface Mapping {
  mapping_id: string
  run_id: string
  source_store_id: string
  source_product_code: string
  source_product_name: string
  source_normalized_name: string | null
  target_store_id: string
  target_product_code: string | null
  target_product_name: string | null
  match_method: MatchMethod
  match_phase: number | null
  confidence: number
  status: MappingStatus
  brand: string | null
  strength: string | null
  unit: string | null
  dosage_form: string | null
  pack_size: string | null
  mrp: number | null
}

export interface Candidate {
  candidate_id: string
  mapping_id: string
  target_product_code: string
  target_product_name: string
  target_normalized_name: string | null
  name_score: number
  brand_score: number
  strength_score: number
  form_score: number
  mrp_score: number
  total_score: number
  brand: string | null
  strength: string | null
  dosage_form: string | null
  mrp: number | null
  reason: string | null
}

export interface MappingDetail extends Mapping {
  candidates: Candidate[]
}

export interface MappingPage {
  total: number
  page: number
  page_size: number
  items: Mapping[]
}

export interface RunSummary {
  run_id: string
  auto: number
  pending: number
  preserved: number
  total: number
  source_count: number
  target_count: number
  supplier_pairs: number
}

export interface MappingDashboard {
  counts: Record<MappingStatus, number>
  total: number
  matched: number
  match_rate: number
  needs_review: number
}

export interface MappingStatistics {
  by_status: Record<string, number>
  by_method: Record<string, number>
}

export interface DictionaryEntry {
  entry_id: string
  tenant_id: string | null
  term: string
  canonical: string | null
  kind: string
  is_active: boolean
  created_at: string
}

export interface AuditRow {
  audit_id: string
  mapping_id: string | null
  run_id: string | null
  action: string
  old_status: string | null
  new_status: string | null
  actor_user_id: string | null
  detail: string | null
  created_at: string
}

export interface MappingFilters {
  status?: MappingStatus
  source_store_id?: string
  target_store_id?: string
  search?: string
  page?: number
  page_size?: number
}

/** A hit from the Correct-Product picker (target store's product master). */
export interface ProductSearchResult {
  product_code: string
  product_name: string
  unit: string | null
  mrp: number | null
  brand: string | null
  strength: string | null
  unit_of_strength: string | null
  dosage_form: string | null
  pack_size: string | null
}

/** One row's decision in a bulk manual-review call. */
export interface BulkReviewItem {
  mapping_id: string
  target_product_code?: string
  target_product_name?: string
}

export interface BulkReviewFailure {
  mapping_id: string
  reason: string
}

export interface BulkReviewResult {
  approved: number
  rejected: number
  skipped: number
  failed: BulkReviewFailure[]
  remaining: number
  approved_today: number
  current_page: number
  next_page: number
  total_pages: number
  has_next: boolean
}

export interface ReviewProgress {
  remaining: number
  approved_today: number
}

/** Keyset cursor for Manual Review continuous batches — pass back verbatim to
 *  fetch the next batch. */
export interface ReviewCursor {
  confidence: number
  mapping_id: string
}

export interface ReviewBatch {
  items: Mapping[]
  has_more: boolean
  next_cursor: ReviewCursor | null
}
