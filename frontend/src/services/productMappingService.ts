import { api } from './apiClient'
import type {
  AuditRow,
  BulkReviewItem,
  BulkReviewResult,
  Candidate,
  DictionaryEntry,
  Mapping,
  MappingDashboard,
  MappingDetail,
  MappingFilters,
  MappingPage,
  MappingStatistics,
  ProductSearchResult,
  ReviewProgress,
  RunSummary,
} from '../types/productMapping'

function qs(params: Record<string, string | number | boolean | undefined>): string {
  const parts = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== '' && v !== null)
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
  return parts.length ? `?${parts.join('&')}` : ''
}

const BASE = '/api/product-mapping'

export const productMappingService = {
  run: (tenantId: string, sourceStoreId: string, targetStoreId: string, actor: string | null) =>
    api.post<RunSummary>(`${BASE}/runs${qs({ tenant_id: tenantId })}`, {
      source_store_id: sourceStoreId,
      target_store_id: targetStoreId,
      actor,
    }),

  mappings: (tenantId: string, f: MappingFilters) =>
    api.get<MappingPage>(`${BASE}/mappings${qs({ tenant_id: tenantId, ...f })}`),

  mapping: (tenantId: string, mappingId: string) =>
    api.get<MappingDetail>(`${BASE}/mappings/${mappingId}${qs({ tenant_id: tenantId })}`),

  candidates: (tenantId: string, mappingId: string) =>
    api.get<Candidate[]>(`${BASE}/mappings/${mappingId}/candidates${qs({ tenant_id: tenantId })}`),

  approve: (
    tenantId: string,
    mappingId: string,
    body: { target_product_code?: string; target_product_name?: string; actor: string | null },
  ) => api.post<Mapping>(`${BASE}/mappings/${mappingId}/approve${qs({ tenant_id: tenantId })}`, body),

  reject: (tenantId: string, mappingId: string, actor: string | null) =>
    api.post<Mapping>(`${BASE}/mappings/${mappingId}/reject${qs({ tenant_id: tenantId })}`, { actor }),

  // --- Manual Review v2 -----------------------------------------------------

  reviewProgress: (tenantId: string, sourceStoreId: string, targetStoreId: string) =>
    api.get<ReviewProgress>(
      `${BASE}/manual-review/progress${qs({ tenant_id: tenantId, source_store_id: sourceStoreId, target_store_id: targetStoreId })}`,
    ),

  bulkReview: (
    tenantId: string,
    body: {
      action: 'APPROVE' | 'REJECT'
      items: BulkReviewItem[]
      source_store_id: string
      target_store_id: string
      page: number
      page_size: number
      actor: string | null
    },
  ) => api.post<BulkReviewResult>(`${BASE}/manual-review/bulk${qs({ tenant_id: tenantId })}`, body),

  searchProducts: (tenantId: string, storeId: string, query: string, limit = 25) =>
    api.get<ProductSearchResult[]>(
      `${BASE}/products/search${qs({ tenant_id: tenantId, store_id: storeId, q: query, limit })}`,
    ),

  dashboard: (tenantId: string, sourceStoreId?: string, targetStoreId?: string) =>
    api.get<MappingDashboard>(
      `${BASE}/dashboard${qs({ tenant_id: tenantId, source_store_id: sourceStoreId, target_store_id: targetStoreId })}`,
    ),

  statistics: (tenantId: string, sourceStoreId?: string, targetStoreId?: string) =>
    api.get<MappingStatistics>(
      `${BASE}/statistics${qs({ tenant_id: tenantId, source_store_id: sourceStoreId, target_store_id: targetStoreId })}`,
    ),

  audit: (tenantId: string, mappingId?: string, page = 1, pageSize = 100) =>
    api.get<AuditRow[]>(
      `${BASE}/audit${qs({ tenant_id: tenantId, mapping_id: mappingId, page, page_size: pageSize })}`,
    ),

  dictionary: (tenantId?: string) =>
    api.get<DictionaryEntry[]>(`${BASE}/dictionary${qs({ tenant_id: tenantId })}`),

  addTerm: (
    body: { term: string; canonical?: string; kind: string; actor: string | null },
    tenantId?: string,
  ) => api.post<{ entry_id: string }>(`${BASE}/dictionary${qs({ tenant_id: tenantId })}`, body),

  updateTerm: (
    entryId: string,
    body: { term?: string; canonical?: string; kind?: string; is_active?: boolean; actor: string | null },
  ) => api.put<{ ok: boolean }>(`${BASE}/dictionary/${entryId}`, body),

  deleteTerm: (entryId: string) => api.delete<{ ok: boolean }>(`${BASE}/dictionary/${entryId}`),
}
