// Centralized backend API client. Adapted from the proven retry/timeout
// pattern in supplier-stock-client/src/api/client.js (per Phase 1
// discovery §1 "its API client has retry-aware integration patterns"),
// reimplemented against this app's own settings/session stores so neither
// existing client's code is imported at runtime.
import { resolveApiBaseUrl } from '../services/settingsStore.js';
import { clearSession, getSession, notifyUnauthorized } from '../services/sessionStore.js';

function joinUrl(baseUrl, path) {
  const base = String(baseUrl || '').replace(/\/+$/, '');
  const suffix = String(path || '').replace(/^\/+/, '');
  return `${base}/${suffix}`;
}

function currentAuth() {
  const token = getSession()?.token || '';
  return {
    token,
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  };
}

// Error text is shown in the renderer. Never leave a bearer token in it,
// even if a response body echoes one back.
function publicErrorMessage(message, token) {
  const text = typeof message === 'string' ? message : '';
  if (token && text.includes(token)) return 'Request failed';
  return text;
}

// Only GET (idempotent, safe to retry) gets automatic retry on a
// transient status. Per Phase 4 §11: "No automatic retry of non-idempotent
// order submissions" — POST/PUT/PATCH/DELETE never retry here, regardless
// of status code.
const TRANSIENT_STATUS = new Set([408, 425, 429, 502, 503, 504]);
const RETRY_DELAYS_MS = [350, 1000];
const FAST_RETRY_TIMEOUT_MS = 8000;
const DEFAULT_TIMEOUT_MS = 30000;

function delay(ms, signal) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms);
    if (!signal) return;
    signal.addEventListener(
      'abort',
      () => {
        clearTimeout(timer);
        reject(new DOMException('Aborted', 'AbortError'));
      },
      { once: true }
    );
  });
}

// FastAPI error bodies aren't always a plain string: 422 validation errors
// send `detail` as a list of {loc, msg, type} objects. Extract readable
// text instead of letting `new Error(x)` stringify it to "[object Object]".
function detailToMessage(data) {
  const detail = data?.detail ?? data?.message ?? data?.error;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => (typeof item === 'string' ? item : `${(item?.loc || []).join('.')}: ${item?.msg || JSON.stringify(item)}`))
      .join('; ');
  }
  if (detail && typeof detail === 'object') return JSON.stringify(detail);
  return detail || '';
}

export class ApiError extends Error {
  constructor(message, { status, data } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

export async function apiRequest(path, options = {}) {
  const method = String(options.method || 'GET').toUpperCase();
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const retries = options.transientRetries ?? (method === 'GET' ? RETRY_DELAYS_MS.length : 0);
  const { timeoutMs: _t, transientRetries: _r, ignoreUnauthorized, skipAuth, ...fetchOptions } = options;

  let lastError;
  for (let attempt = 0; attempt <= retries; attempt += 1) {
    const isLastAttempt = attempt === retries;
    const attemptTimeoutMs = isLastAttempt ? timeoutMs : Math.min(FAST_RETRY_TIMEOUT_MS, timeoutMs);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), attemptTimeoutMs);
    if (options.signal) {
      if (options.signal.aborted) controller.abort();
      else options.signal.addEventListener('abort', () => controller.abort(), { once: true });
    }

    try {
      const auth = skipAuth ? { token: '', headers: {} } : currentAuth();
      const response = await fetch(joinUrl(resolveApiBaseUrl(), path), {
        ...fetchOptions,
        signal: controller.signal,
        headers: {
          Accept: 'application/json',
          ...(options.body && !(options.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}),
          ...auth.headers,
          ...(options.headers || {}),
        },
      });
      clearTimeout(timer);

      if (TRANSIENT_STATUS.has(response.status) && !isLastAttempt) {
        await delay(RETRY_DELAYS_MS[attempt] ?? 1000, options.signal);
        continue;
      }

      const contentType = response.headers.get('content-type') || '';
      const data = contentType.includes('application/json') ? await response.json().catch(() => null) : await response.text();

      if (!response.ok) {
        const message = publicErrorMessage(
          detailToMessage(data) || `Request failed with status ${response.status}`,
          auth.token
        );
        // A 401 on a request that sent a bearer token means the session is
        // missing, expired, or was replaced. Login's own 401 (no token yet)
        // must not take this path. Logout passes ignoreUnauthorized so a
        // rejected sign-out cannot recurse.
        if (response.status === 401 && auth.token && !ignoreUnauthorized) {
          clearSession();
          notifyUnauthorized(message);
        }
        throw new ApiError(message, {
          status: response.status,
          data,
        });
      }
      return data;
    } catch (err) {
      clearTimeout(timer);
      lastError = err;
      if (err.name === 'AbortError' && !isLastAttempt) {
        continue;
      }
      if (err instanceof ApiError) throw err;
      if (err.name === 'AbortError') {
        throw new ApiError('Request timed out', { status: 0 });
      }
      throw new ApiError(err.message || 'Network request failed', { status: 0 });
    }
  }
  throw lastError;
}

export function apiGet(path, options) {
  return apiRequest(path, { ...options, method: 'GET' });
}

export function apiPost(path, body, options) {
  return apiRequest(path, { ...options, method: 'POST', body: JSON.stringify(body) });
}

export function apiPut(path, body, options) {
  return apiRequest(path, { ...options, method: 'PUT', body: JSON.stringify(body) });
}

export function apiPatch(path, body, options) {
  return apiRequest(path, { ...options, method: 'PATCH', body: JSON.stringify(body) });
}

export function apiDelete(path, options) {
  return apiRequest(path, { ...options, method: 'DELETE' });
}
