import { STORAGE_KEYS } from '../utils/storageKeys'

/**
 * JWT-ready token storage. UI-01B uses localStorage; the implementation can be
 * swapped (e.g. for secure cookie handling) without touching consumers.
 */
export const tokenStorage = {
  get(): string | null {
    return localStorage.getItem(STORAGE_KEYS.token)
  },
  set(token: string): void {
    localStorage.setItem(STORAGE_KEYS.token, token)
  },
  clear(): void {
    localStorage.removeItem(STORAGE_KEYS.token)
  },
}
