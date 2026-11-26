// Stand-in for frontend/src/services/apiClient.ts.
// Vite redirects that module here so embedded web pages keep their call
// sites and this app's in-memory session supplies the bearer token.
// The token is not copied into localStorage.
import { apiRequest, ApiError as DesktopApiError } from '../api/client.js';
import { resolveApiBaseUrl } from '../services/settingsStore.js';
import { getSession } from '../services/sessionStore.js';

// Kept for any existing display/debug reads -- NOT used for requests below,
// since a value captured once at module load would never pick up a Settings
// change or a LAN<->public failover. Use resolveApiBaseUrl() for an actual URL.
export const API_BASE_URL = resolveApiBaseUrl();

export class ApiError extends Error {
  constructor(message, status) {
    super(typeof message === 'string' && message ? message : 'Request failed');
    this.name = 'ApiError';
    this.status = Number.isFinite(status) ? status : 0;
  }
}

function toApiError(err) {
  if (err instanceof ApiError) return err;
  if (err instanceof DesktopApiError) return new ApiError(err.message, err.status);
  return new ApiError(err?.message || 'Request failed', err?.status ?? 0);
}

function readOptions(signalOrOptions) {
  if (!signalOrOptions) return {};
  if (typeof AbortSignal !== 'undefined' && signalOrOptions instanceof AbortSignal) {
    return { signal: signalOrOptions };
  }
  return {
    signal: signalOrOptions.signal,
    timeoutMs: signalOrOptions.timeoutMs,
    transientRetries: signalOrOptions.retries,
  };
}

async function call(path, options) {
  try {
    return await apiRequest(path, options);
  } catch (err) {
    throw toApiError(err);
  }
}

async function raw(path, init) {
  const token = getSession()?.token || '';
  const headers = { ...(init.headers || {}) };
  if (token && !headers.Authorization) headers.Authorization = `Bearer ${token}`;
  let response;
  try {
    response = await fetch(`${resolveApiBaseUrl()}${path}`, { ...init, headers });
  } catch {
    throw new ApiError('Unable to reach the server. Check that the API is running.', 0);
  }
  if (!response.ok) {
    let detail = response.statusText || 'Request failed';
    try {
      const body = await response.json();
      detail = body.detail ?? body.error ?? detail;
    } catch {
      // no JSON body
    }
    if (detail && typeof detail !== 'string') detail = JSON.stringify(detail);
    throw new ApiError(detail, response.status);
  }
  return response;
}

export const api = {
  get: (path, signalOrOptions) => call(path, { method: 'GET', ...readOptions(signalOrOptions) }),
  post: (path, body) => call(path, {
    method: 'POST',
    body: body === undefined ? undefined : JSON.stringify(body),
  }),
  upload: (path, form) => call(path, { method: 'POST', body: form }),
  put: (path, body) => call(path, {
    method: 'PUT',
    body: body === undefined ? undefined : JSON.stringify(body),
  }),
  patch: (path, body) => call(path, {
    method: 'PATCH',
    body: body === undefined ? undefined : JSON.stringify(body),
  }),
  delete: (path, body) => call(path, {
    method: 'DELETE',
    body: body === undefined ? undefined : JSON.stringify(body),
  }),
  blob: async (path) => (await raw(path, { method: 'GET' })).blob(),
  postBlob: async (path, body) => (await raw(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })).blob(),
  postBlobMeta: async (path, body) => {
    const response = await raw(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    return { blob: await response.blob(), headers: response.headers };
  },
  uploadBlobMeta: async (path, form) => {
    const response = await raw(path, { method: 'POST', body: form });
    return { blob: await response.blob(), headers: response.headers };
  },
};
