import { tokenStorage } from './tokenStorage'
import { logger } from '../platform/logging/Logger'

// Runtime override (window.__UNINEX_API_BASE__, injected by /config.js in
// production deployments) takes precedence over the build-time env, so the same
// production bundle can be pointed at any HO server without rebuilding.
//
// An explicitly-set EMPTY string means "same origin" (relative) — the SPA then
// calls whichever host served it (LAN IP, domain, static IP), so one deployment
// works over every route. It is only ignored when the property is absent (dev),
// where we fall back to the build-time env or localhost.
const runtimeBase =
  typeof window !== 'undefined'
    ? (window as unknown as { __UNINEX_API_BASE__?: string }).__UNINEX_API_BASE__
    : undefined
// Build-time env. An explicitly-set value (including an empty string) wins; only
// when the variable is entirely absent do we fall back to localhost. An empty
// string means "same origin" (relative), so in development requests go to the
// Vite dev server and are proxied to the API (see vite.config.ts) — this avoids
// cross-origin CORS and ERR_CONNECTION_REFUSED regardless of the host/IP used to
// open the SPA.
const buildBase = import.meta.env.VITE_API_BASE_URL
const BASE_URL =
  runtimeBase !== undefined && runtimeBase !== null
    ? runtimeBase
    : buildBase !== undefined
      ? buildBase
      : 'http://localhost:8000'

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

interface RequestOptions extends Omit<RequestInit, 'signal'> {
  signal?: AbortSignal
  /**
   * Aborts the request after this many ms. Omitted (the default for every
   * existing call site) means no timeout — behavior is unchanged from before
   * this option existed. New/platform code opts in explicitly.
   */
  timeoutMs?: number
  /**
   * Automatic retries on total network failure (server unreachable — never on
   * a reached-but-erroring server, i.e. never for 4xx/5xx). Defaults to 0
   * (no retry, existing behavior). Only meaningful for idempotent calls —
   * post/put/patch/delete don't expose this to avoid duplicating writes.
   */
  retries?: number
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { timeoutMs, retries = 0, signal: callerSignal, ...init } = options
  const token = tokenStorage.get()
  // For multipart uploads let the browser set Content-Type (with the boundary).
  const isForm = typeof FormData !== 'undefined' && init.body instanceof FormData
  const headers: Record<string, string> = {
    ...(isForm ? {} : { 'Content-Type': 'application/json' }),
    ...(init.headers as Record<string, string> | undefined),
  }
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }
  const method = init.method ?? 'GET'

  for (let attempt = 0; ; attempt++) {
    const timeoutSignal = timeoutMs ? AbortSignal.timeout(timeoutMs) : undefined
    const signal =
      callerSignal && timeoutSignal ? AbortSignal.any([callerSignal, timeoutSignal]) : (callerSignal ?? timeoutSignal)

    let response: Response
    try {
      response = await fetch(`${BASE_URL}${path}`, { ...init, headers, signal })
    } catch (e) {
      // A caller-triggered abort (component unmounted / a newer request superseded
      // this one) is not a request failure — let the caller's own `catch` decide
      // whether to ignore it (they already checked signal.aborted / a "live" flag).
      // A timeout-triggered abort, on the other hand, is a real failure.
      if (e instanceof DOMException && e.name === 'AbortError') {
        if (timeoutSignal?.aborted && !callerSignal?.aborted) {
          throw new ApiError('Request timed out.', 0)
        }
        throw e
      }
      if (attempt < retries) {
        await new Promise((resolve) => setTimeout(resolve, 400 * (attempt + 1)))
        continue
      }
      logger.error('api-client', `${method} ${path} unreachable`, e)
      throw new ApiError('Unable to reach the server. Check that the API is running.', 0)
    }

    if (!response.ok) {
      let detail = response.statusText || 'Request failed'
      try {
        const body = await response.json()
        detail = body.detail ?? body.error ?? detail
      } catch {
        // response had no JSON body
      }
      logger.error('api-client', `${method} ${path} failed (${response.status})`, detail)
      throw new ApiError(detail, response.status)
    }

    if (response.status === 204) {
      return undefined as T
    }
    return (await response.json()) as T
  }
}

export const api = {
  // `signal` lets a caller cancel an in-flight GET (e.g. via AbortController)
  // when a newer request supersedes it — avoids a slow, stale response from an
  // earlier render/keystroke overwriting fresher state. Optional and additive;
  // every existing call site is unaffected. Passing an options object instead
  // (new, opt-in) additionally allows a timeout and/or retry count.
  get: <T>(path: string, signalOrOptions?: AbortSignal | Pick<RequestOptions, 'signal' | 'timeoutMs' | 'retries'>) =>
    request<T>(path, signalOrOptions instanceof AbortSignal ? { signal: signalOrOptions } : signalOrOptions),
  post: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'POST', body: JSON.stringify(body) }),
  upload: <T>(path: string, form: FormData) =>
    request<T>(path, { method: 'POST', body: form }),
  put: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PUT', body: JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
  delete: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'DELETE',
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  // Fetch a binary payload (file downloads). Same base URL + auth handling as
  // request(), but returns the raw Blob instead of parsing JSON.
  blob: async (path: string): Promise<Blob> => {
    const token = tokenStorage.get()
    const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {}
    let response: Response
    try {
      response = await fetch(`${BASE_URL}${path}`, { headers })
    } catch {
      throw new ApiError('Unable to reach the server. Check that the API is running.', 0)
    }
    if (!response.ok) {
      throw new ApiError(response.statusText || 'Download failed', response.status)
    }
    return response.blob()
  },
}
