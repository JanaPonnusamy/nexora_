// Uses the existing, unmodified backend contract — verified against
// backend/controllers/auth_controller.py:
//   POST /api/auth/login  {username, password} -> {token, token_type, user} (:32-146)
//   POST /api/auth/logout (Bearer auth)         -> {ok: true}, releases the
//                                                   single-session lease (:149-155)
// No new backend endpoint is invented here, per Phase 4 §11.
import { apiPost, ApiError } from '../api/client.js';
import { setSession, clearSession, getSession } from './sessionStore.js';

export async function login(username, password, options = {}) {
  const result = await apiPost('/api/auth/login', { username, password });
  if (!result || typeof result.token !== 'string' || !result.token) {
    throw new ApiError('Login did not return a session', { status: 0 });
  }
  setSession(
    { token: result.token, user: result.user ?? null },
    { remember: options.remember !== false }
  );
  return result.user ?? null;
}

export async function logout() {
  try {
    // Best-effort: release the server-side session lease so the user can
    // sign in elsewhere immediately. Local session is cleared regardless
    // of whether this call succeeds (e.g. backend unreachable) — the user
    // must always be able to log out of the client even if the server
    // can't be reached. ignoreUnauthorized: a 401 here must not recurse
    // through the unauthorized handler, which would call logout again.
    await apiPost('/api/auth/logout', {}, { ignoreUnauthorized: true });
  } catch {
    // Ignore — local sign-out below still proceeds.
  } finally {
    clearSession();
  }
}

export function currentUser() {
  return getSession()?.user ?? null;
}

// Dev-only skip-login (mirrors desktop/supplier-stock-client's own
// VITE_DEV_LOGIN_USER/PASS precedent, but does NOT call /api/auth/login --
// that still needs a live DB, which is exactly what this is for working
// around). Fabricates a local session with no server round-trip, so the app
// shell is reachable while HO's SQL Server is unreachable. Every
// subsequent real API call still hits the live backend and fails/401s on
// its own; this only unblocks getting past the login screen. Gated by
// import.meta.env.DEV so the whole path is stripped from production/
// packaged builds, same as supplier-stock-client's bypass.
export function devSkipLogin() {
  if (!import.meta.env.DEV) return null;
  const enabled = String(import.meta.env.VITE_DEV_SKIP_LOGIN || '').trim() === '1';
  if (!enabled) return null;
  const user = {
    username: import.meta.env.VITE_DEV_SKIP_LOGIN_USER || 'dev-offline',
    first_name: 'Dev',
    is_platform_user: true,
    tenant_id: import.meta.env.VITE_DEV_SKIP_LOGIN_TENANT || '',
    roles: [{ role: 'SUPER_ADMIN', store_id: import.meta.env.VITE_DEV_SKIP_LOGIN_STORE || '' }],
  };
  // A fake, unsigned JWT-shaped token so sessionStore's own exp-parsing
  // (tokenExpiresAtMs) degrades gracefully (no exp claim -> never expires
  // locally); it will simply be rejected by the backend on any real call.
  const fakeToken = 'dev.' + btoa(JSON.stringify({ sub: user.username })) + '.offline';
  setSession({ token: fakeToken, user }, { remember: false });
  return user;
}

export { ApiError };
