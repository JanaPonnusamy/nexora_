import { api } from './apiClient'
import type {
  CorrectionPage,
  DocImportItem,
  DocImportRow,
  HeaderPatch,
  ImportDetail,
  ImportListPage,
  ItemPatch,
  ReviewPayload,
  SupplierAssignRequest,
  UploadResponse,
} from '../types/documentExtraction'

function qs(params: Record<string, string | number | boolean | undefined>): string {
  const parts = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== '' && v !== null)
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
  return parts.length ? `?${parts.join('&')}` : ''
}

const BASE = '/api/document-extraction'

export const documentExtractionService = {
  listImports: (tenantId: string, storeId?: string, page = 1, pageSize = 25) =>
    api.get<ImportListPage>(
      `${BASE}/imports${qs({ tenant_id: tenantId, store_id: storeId, page, page_size: pageSize })}`,
    ),

  // One doc_import row per invoice — `files` may be several pages of the
  // same invoice (grouped server-side by group_as_single_invoice=true).
  uploadFiles: (files: File[], tenantId: string, storeId: string, actor?: string | null) => {
    const form = new FormData()
    for (const f of files) form.append('files', f)
    form.append('group_as_single_invoice', 'true')
    return api.upload<UploadResponse>(
      `${BASE}/imports${qs({ tenant_id: tenantId, store_id: storeId, actor: actor ?? undefined })}`,
      form,
    )
  },

  // The pipeline stages are separate endpoints on the backend (not
  // auto-chained server-side) — documentExtractionPipeline.ts runs them in
  // sequence right after upload so the operator lands on a populated
  // review, not an empty shell they have to manually "process".
  runPreprocess: (importId: number | string, actor?: string | null) =>
    api.post<DocImportRow>(`${BASE}/imports/${importId}/preprocess${qs({ actor: actor ?? undefined })}`, {}),
  runOcr: (importId: number | string, actor?: string | null) =>
    api.post<DocImportRow>(`${BASE}/imports/${importId}/ocr${qs({ actor: actor ?? undefined })}`, {}),
  runExtract: (importId: number | string, actor?: string | null) =>
    api.post<DocImportRow>(`${BASE}/imports/${importId}/extract${qs({ actor: actor ?? undefined })}`, {}),
  runValidate: (importId: number | string, actor?: string | null) =>
    api.post<DocImportRow>(`${BASE}/imports/${importId}/validate${qs({ actor: actor ?? undefined })}`, {}),

  review: (importId: number | string) => api.get<ReviewPayload>(`${BASE}/imports/${importId}/review`),

  updateHeader: (importId: number | string, body: HeaderPatch) =>
    api.patch<DocImportRow>(`${BASE}/imports/${importId}/header`, body),

  updateItem: (importId: number | string, itemId: number | string, body: ItemPatch) =>
    api.patch<DocImportItem>(`${BASE}/imports/${importId}/items/${itemId}`, body),

  excludeItem: (importId: number | string, itemId: number | string, actor?: string | null) =>
    api.post<DocImportItem>(`${BASE}/imports/${importId}/items/${itemId}/exclude${qs({ actor: actor ?? undefined })}`, {}),

  assignSupplier: (importId: number | string, body: SupplierAssignRequest) =>
    api.post<DocImportRow>(`${BASE}/imports/${importId}/supplier`, body),

  save: (importId: number | string, force: boolean, actor?: string | null) =>
    api.post<DocImportRow>(`${BASE}/imports/${importId}/save`, { force, actor }),

  importDetail: (importId: number | string) => api.get<ImportDetail>(`${BASE}/imports/${importId}`),

  corrections: (importId: number | string, page = 1, pageSize = 100) =>
    api.get<CorrectionPage>(`${BASE}/imports/${importId}/corrections${qs({ page, page_size: pageSize })}`),

  deleteImport: (importId: number | string, actor?: string | null) =>
    api.delete<void>(`${BASE}/imports/${importId}${qs({ actor: actor ?? undefined })}`),

  reprocess: (importId: number | string, fromStage: string, actor?: string | null) =>
    api.post<DocImportRow>(`${BASE}/imports/${importId}/reprocess`, { from_stage: fromStage, actor }),

  exportImports: (importIds: number[], fileFormat: 'xlsx' | 'csv', actor?: string | null) =>
    api.post<{ export_batch_id: string; row_count: number; file_format: string; download_url: string }>(
      `${BASE}/exports`,
      { import_ids: importIds, file_format: fileFormat, actor },
    ),

  originalImagePath: (importId: number | string, page = 1) => `${BASE}/imports/${importId}/original${qs({ page })}`,
  previewImagePath: (importId: number | string, page = 1) => `${BASE}/imports/${importId}/preview${qs({ page })}`,
}
