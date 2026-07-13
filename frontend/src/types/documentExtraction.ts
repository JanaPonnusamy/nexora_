/** Mirrors dbo.doc_import (see backend/modules/document_extraction/repository.py
 *  get_import / list_imports) — every field the Review screen can read or
 *  PATCH. Optional/nullable throughout since a row this early in the
 *  pipeline may not have every stage's fields populated yet. */
export interface DocImportRow {
  import_id: number
  import_guid: string
  status: string
  failure_reason: string | null
  is_upload_completed: boolean
  is_image_processed: boolean
  is_ocr_completed: boolean
  is_header_extracted: boolean
  is_items_extracted: boolean
  ocr_confidence: number | null
  source_type: string
  supplier_name: string | null
  gst_number: string | null
  dl_number: string | null
  supplier_phone: string | null
  supplier_address: string | null
  matched_supplier_code: string | null
  supplier_match_method: string | null
  supplier_match_confidence: number | null
  is_supplier_unknown: boolean
  invoice_number: string | null
  invoice_date: string | null
  invoice_type: string | null
  order_number: string | null
  transport: string | null
  salesman: string | null
  credit_days: number | null
  gross_amount: number | null
  discount_amount: number | null
  scheme_discount: number | null
  cash_discount: number | null
  taxable_amount: number | null
  cgst_amount: number | null
  sgst_amount: number | null
  igst_amount: number | null
  cess_amount: number | null
  round_off: number | null
  net_amount: number | null
  item_count: number | null
  total_quantity: number | null
  irn_number: string | null
  ack_number: string | null
  ack_date: string | null
  validation_status: string
  preview_image_path: string | null
  page_count: number | null
  uploaded_at: string
  /** Only ever set by POST .../ocr: the imports OCR split out of this upload
   *  because the batch turned out to hold more than one invoice. They are
   *  already fully extracted and validated by the time this comes back — the
   *  operator finds them in History, not in this job. */
  split_import_ids?: number[]
}

/** Mirrors dbo.doc_import_item (repository.list_items). */
export interface DocImportItem {
  item_id: number
  import_id: number
  line_number: number
  product_code: string | null
  product_guid: string | null
  ocr_product_name: string
  normalized_product_name: string | null
  pack: string | null
  hsn_code: string | null
  batch_number: string | null
  expiry_raw: string | null
  expiry_date: string | null
  quantity: number | null
  free_quantity: number | null
  ptr: number | null
  purchase_rate: number | null
  mrp: number | null
  gst_percent: number | null
  discount_percent: number | null
  discount_amount: number | null
  amount: number | null
  confidence: number | null
  is_excluded: boolean
}

export interface ValidationFinding {
  rule_code: string
  severity: 'ERROR' | 'WARNING'
  field?: string | null
  item_id?: number | null
  message: string
  expected_value?: string | null
  actual_value?: string | null
}

export interface ReviewPayload {
  import_id: number
  status: string
  supplier: {
    matched_supplier_code: string | null
    supplier_name: string | null
    gst_number: string | null
    dl_number: string | null
    supplier_match_method: string | null
    supplier_match_confidence: number | null
    is_supplier_unknown: boolean
  }
  header: DocImportRow
  items: DocImportItem[]
  validation: {
    import_id: number
    validation_status: string
    findings: ValidationFinding[]
  }
  preview_image_path: string | null
}

export interface ImportListRow {
  import_id: number
  import_guid: string
  status: string
  source_type: string
  supplier_name: string | null
  matched_supplier_code: string | null
  is_supplier_unknown: boolean
  invoice_number: string | null
  invoice_date: string | null
  net_amount: number | null
  validation_status: string
  is_duplicate: boolean
  uploaded_by: string
  uploaded_at: string
  reviewed_at: string | null
  saved_at: string | null
}

export interface ImportListPage {
  items: ImportListRow[]
  total: number
  page: number
  page_size: number
}

export interface ExportHistoryEntry {
  export_id: number
  export_batch_id: string
  import_id: number
  file_format: string
  storage_path: string | null
  row_count: number | null
  exported_by: string
  exported_at: string
}

export interface ImportDetail {
  import: DocImportRow
  items: DocImportItem[]
  exports: ExportHistoryEntry[]
}

export interface CorrectionEntry {
  review_id: number
  import_id: number
  item_id: number | null
  field_name: string
  old_value: string | null
  new_value: string | null
  corrected_by: string
  corrected_at: string
}

export interface CorrectionPage {
  items: CorrectionEntry[]
  total: number
  page: number
  page_size: number
}

export type HeaderPatch = Partial<
  Pick<
    DocImportRow,
    | 'invoice_number' | 'invoice_date' | 'invoice_type' | 'order_number' | 'transport'
    | 'salesman' | 'credit_days' | 'supplier_name' | 'gst_number' | 'dl_number'
    | 'gross_amount' | 'discount_amount' | 'scheme_discount' | 'cash_discount'
    | 'taxable_amount' | 'cgst_amount' | 'sgst_amount' | 'igst_amount' | 'cess_amount'
    | 'round_off' | 'net_amount' | 'item_count' | 'total_quantity'
    | 'irn_number' | 'ack_number' | 'ack_date'
  >
> & { actor?: string | null }

export type ItemPatch = Partial<
  Pick<
    DocImportItem,
    | 'normalized_product_name' | 'pack' | 'hsn_code' | 'batch_number' | 'expiry_raw'
    | 'expiry_date' | 'quantity' | 'free_quantity' | 'ptr' | 'purchase_rate' | 'mrp'
    | 'gst_percent' | 'discount_percent' | 'discount_amount' | 'amount'
  >
> & { actor?: string | null }

export interface SupplierAssignRequest {
  matched_supplier_code?: string | null
  supplier_name?: string | null
  gst_number?: string | null
  dl_number?: string | null
  actor?: string | null
}

export interface UploadResponse {
  imports: DocImportRow[]
}
