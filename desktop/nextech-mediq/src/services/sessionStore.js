// Session persistence.
//
// The bearer token is not stored in renderer localStorage. A copied token in
// localStorage is readable by any script running in the page. This module
// keeps the working copy in renderer memory (fetch has to attach it) and,
// when the operator asks to remember the session, asks the Electron main
// process to write it with safeStorage. That disk copy is not a server-side
// revoke. Platform-user JWTs have no session id; POST /api/auth/logout does
// not invalidate them. Logout here only drops the local copies.
//
// A legacy localStorage record under nextechMediq.session is read once and
// removed so an older build does not leave the token behind.

const SESSION_KEY = 'nextechMediq.session';

export const UNAUTHORIZED_EVENT = 'nextech-mediq:unauthorized';

let sessionEndReason = null;
let memory = null;

export function consumeSessionEndReason() {
  const reason = sessionEndReason;
  sessionEndReason = null;
  return reason;
}

export function notifyUnauthorized(message) {
  const text = message || 'Your session is no longer valid. Sign in again.';
  sessionEndReason = text;
  const target = globalThis.window;
  if (!target || typeof target.dispatchEvent !== 'function' || typeof CustomEvent !== 'function') return;
  target.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT, { detail: { message: text } }));
}

function decodeBase64Url(segment) {
  const pad = segment.length % 4 === 0 ? '' : '='.repeat(4 - (segment.length % 4));
  const normalized = segment.replace(/-/g, '+').replace(/_/g, '/') + pad;
  if (typeof globalThis.atob === 'function') return globalThis.atob(normalized);
  return Buffer.from(normalized, 'base64').toString('utf8');
}

export function tokenExpiresAtMs(token) {
  if (typeof token !== 'string') return null;
  const parts = token.split('.');
  if (parts.length < 2 || !parts[1]) return null;
  try {
    const payload = JSON.parse(decodeBase64Url(parts[1]));
    if (typeof payload?.exp !== 'number' || !Number.isFinite(payload.exp)) return null;
    return payload.exp * 1000;
  } catch {
    return null;
  }
}

function storage() {
  return globalThis.window?.localStorage || null;
}

function vault() {
  return globalThis.window?.nextechMediq?.session || null;
}

function readLegacy() {
  try {
    const raw = storage()?.getItem(SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch {
    return null;
  }
}

function dropLegacy() {
  try {
    storage()?.removeItem(SESSION_KEY);
  } catch {
    // Best-effort only.
  }
}

function persistVault(session) {
  const api = vault();
  if (!api) return;
  const job = session && session.remember !== false ? api.set(session) : api.clear?.();
  Promise.resolve(job).catch(() => {});
}

function accept(session) {
  if (!session?.token) return null;
  // No calendar-day cutoff: the operator stays signed in across days (owner
  // decision 2026-11-24, "one time login life time") -- the JWT's own `exp`
  // claim below is the only thing that ever ends a remembered session.
  const expiresAt = tokenExpiresAtMs(session.token);
  if (expiresAt != null && Date.now() >= expiresAt) {
    clearSession();
    notifyUnauthorized('Token expired');
    return null;
  }
  return session;
}

export async function hydrateSession() {
  const api = vault();
  if (api?.get) {
    try {
      const stored = await api.get();
      if (stored?.token) memory = stored;
    } catch {
      // The window still works with a memory session if the vault cannot be read.
    }
  }
  if (!memory?.token) {
    const legacy = readLegacy();
    if (legacy?.token) {
      memory = legacy;
      persistVault(legacy);
    }
  }
  dropLegacy();
  return getSession();
}

export function getSession() {
  if (!memory?.token) {
    const legacy = readLegacy();
    if (legacy?.token) {
      memory = legacy;
      dropLegacy();
      if (legacy.remember !== false) persistVault(legacy);
    }
  }
  return accept(memory);
}

export function setSession(session, options = {}) {
  if (!session?.token) return;
  const expiresAt = tokenExpiresAtMs(session.token);
  const stored = {
    token: session.token,
    user: session.user ?? null,
    loginDate: new Date().toDateString(),
    remember: options.remember !== false,
  };
  if (expiresAt != null) stored.expiresAt = expiresAt;
  memory = stored;
  dropLegacy();
  persistVault(stored);
}

export function clearSession() {
  memory = null;
  dropLegacy();
  const api = vault();
  if (api?.clear) Promise.resolve(api.clear()).catch(() => {});
}

export function isAuthenticated() {
  return Boolean(getSession()?.token);
}

export function resetSessionState() {
  memory = null;
  sessionEndReason = null;
}
