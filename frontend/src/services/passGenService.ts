import { api } from './apiClient'
import type { PassGenRequest, PassGenResponse, PassGenStore } from '../types/passGen'

export const passGenService = {
  listStores: () => api.get<PassGenStore[]>('/api/pass-gen/stores'),
  setStoreCode: (storeId: string, numericCode: number | null) =>
    api.put<PassGenStore[]>(`/api/pass-gen/stores/${storeId}/code`, { numeric_code: numericCode }),
  generate: (request: PassGenRequest) =>
    api.post<PassGenResponse>('/api/pass-gen/generate', request),
}
