import { afterEach, describe, expect, it, vi } from 'vitest'

// apiClient.ts calls tokenStorage.get() (bare `localStorage`) on every
// request; stub it before importing so this test can run under vitest's
// plain 'node' environment without pulling in jsdom as a new dependency.
const store = new Map<string, string>()
vi.stubGlobal('localStorage', {
  getItem: (key: string) => store.get(key) ?? null,
  setItem: (key: string, value: string) => store.set(key, value),
  removeItem: (key: string) => store.delete(key),
})

const { api, ApiError } = await import('./apiClient')

describe('apiClient retry/timeout (additive — see RequestOptions)', () => {
  const originalFetch = globalThis.fetch

  afterEach(() => {
    globalThis.fetch = originalFetch
    vi.restoreAllMocks()
  })

  it('does not retry by default — existing call sites see unchanged behavior', async () => {
    let calls = 0
    globalThis.fetch = vi.fn(() => {
      calls += 1
      return Promise.reject(new TypeError('network fail'))
    }) as unknown as typeof fetch

    await expect(api.get('/x')).rejects.toBeInstanceOf(ApiError)
    expect(calls).toBe(1)
  })

  it('retries a GET on total network failure when retries is set, then succeeds', async () => {
    let calls = 0
    globalThis.fetch = vi.fn(() => {
      calls += 1
      if (calls < 3) return Promise.reject(new TypeError('network fail'))
      return Promise.resolve(new Response(JSON.stringify({ ok: true }), { status: 200 }))
    }) as unknown as typeof fetch

    const result = await api.get<{ ok: boolean }>('/x', { retries: 2 })
    expect(result).toEqual({ ok: true })
    expect(calls).toBe(3)
  })

  it('gives up after exhausting retries', async () => {
    let calls = 0
    globalThis.fetch = vi.fn(() => {
      calls += 1
      return Promise.reject(new TypeError('network fail'))
    }) as unknown as typeof fetch

    await expect(api.get('/x', { retries: 2 })).rejects.toBeInstanceOf(ApiError)
    expect(calls).toBe(3) // initial attempt + 2 retries
  })

  it('times out when the server never responds, surfacing a clear ApiError', async () => {
    globalThis.fetch = vi.fn((_url: string, init?: RequestInit) => {
      return new Promise((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
      })
    }) as unknown as typeof fetch

    await expect(api.get('/x', { timeoutMs: 20 })).rejects.toMatchObject({ message: 'Request timed out.' })
  })

  it('still rethrows a caller-triggered abort as AbortError, not ApiError (existing behavior)', async () => {
    globalThis.fetch = vi.fn((_url: string, init?: RequestInit) => {
      return new Promise((_resolve, reject) => {
        init?.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
      })
    }) as unknown as typeof fetch

    const controller = new AbortController()
    const promise = api.get('/x', controller.signal)
    controller.abort()
    await expect(promise).rejects.toMatchObject({ name: 'AbortError' })
  })

  it('does not retry non-network (4xx/5xx) failures', async () => {
    let calls = 0
    globalThis.fetch = vi.fn(() => {
      calls += 1
      return Promise.resolve(new Response(JSON.stringify({ detail: 'nope' }), { status: 500 }))
    }) as unknown as typeof fetch

    await expect(api.get('/x', { retries: 3 })).rejects.toMatchObject({ status: 500 })
    expect(calls).toBe(1)
  })
})
