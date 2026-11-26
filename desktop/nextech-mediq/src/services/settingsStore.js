// App settings persistence. Separate storage key/namespace from either
// existing client (`nexora.desktop.settings` in supplier-stock-client) so
// installing NexTech MediQ Workspace alongside the old clients on the same machine
// cannot collide with or corrupt their stored preferences.
const SETTINGS_KEY = 'nextechMediq.settings';

// Defaults: main HO, LAN first then the public port as a fallback for
// anywhere off the store LAN -- same LAN-first convention as the standalone
// Quick Stock kiosk app and store_agent/config.py's HO_API_URLS. Runtime-
// editable from Settings (owner decision 2026-11-24, reversing the earlier
// "never read a saved host" design): a build-time VITE_API_BASE_URL still
// overrides everything below, for a dev build pinned at one specific host.
export const DEFAULT_LAN_URL = 'http://192.168.10.73:8000';
export const DEFAULT_PUBLIC_URL = 'http://122.252.246.181:8443';
export const DEFAULT_API_BASE_URL = DEFAULT_LAN_URL;

function sanitizeUrl(value) {
  const candidate = String(value || '').trim().replace(/\/+$/, '');
  if (!/^https?:\/\/[^\s]+$/i.test(candidate)) return '';
  if (candidate.includes('192.168.10.32')) return ''; // a different HO environment, never this app's backend
  return candidate;
}

export function defaultSettings() {
  return {
    apiBaseUrl: DEFAULT_API_BASE_URL,
    lanUrl: DEFAULT_LAN_URL,
    publicUrl: DEFAULT_PUBLIC_URL,
    tenantId: '',
    storeId: '',
    storeName: '',
  };
}

export function loadSettings() {
  try {
    const raw = window.localStorage.getItem(SETTINGS_KEY);
    if (!raw) return defaultSettings();
    const parsed = JSON.parse(raw);
    return { ...defaultSettings(), ...parsed };
  } catch {
    return defaultSettings();
  }
}

export function saveSettings(partial) {
  const next = { ...loadSettings(), ...partial };
  try {
    window.localStorage.setItem(SETTINGS_KEY, JSON.stringify(next));
  } catch {
    // Best-effort only — a private/cleared profile must not crash Settings.
  }
  invalidateActiveUrlCache();
  return next;
}

/** The two candidate URLs, in LAN-first order, from saved Settings
 *  (falling back to the shipped defaults for any blank/invalid field). */
export function getHoUrlCandidates() {
  const stored = loadSettings();
  const lan = sanitizeUrl(stored.lanUrl) || DEFAULT_LAN_URL;
  const pub = sanitizeUrl(stored.publicUrl) || DEFAULT_PUBLIC_URL;
  return lan === pub ? [lan] : [lan, pub];
}

// Background LAN/public probing. resolveApiBaseUrl() must stay synchronous
// (every caller builds a fetch() URL immediately), so a probe can only ever
// update the cache for requests AFTER this one. Throttled -- this must never
// turn into "one extra /health fetch per API call", which would double
// network traffic and, in tests, pollute a mocked fetch's call count.
let cachedActiveUrl = null;
let probeInFlight = null;
let lastProbeAt = 0;
const PROBE_TIMEOUT_MS = 2500;
const PROBE_THROTTLE_MS = 60_000;

function probe(url) {
  return new Promise((resolve) => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), PROBE_TIMEOUT_MS);
    fetch(`${url.replace(/\/+$/, '')}/health`, { signal: controller.signal })
      .then((res) => resolve(res.ok))
      .catch(() => resolve(false))
      .finally(() => clearTimeout(timer));
  });
}

function invalidateActiveUrlCache() {
  cachedActiveUrl = null;
  probeInFlight = null;
  lastProbeAt = 0;
}

/** Kicks off (at most once concurrently, at most once per PROBE_THROTTLE_MS)
 *  a background probe of every candidate in order, caching the first
 *  reachable one for subsequent resolveApiBaseUrl() calls. */
function refreshActiveUrlInBackground(candidates) {
  if (probeInFlight) return;
  if (Date.now() - lastProbeAt < PROBE_THROTTLE_MS) return;
  lastProbeAt = Date.now();
  probeInFlight = (async () => {
    for (const url of candidates) {
      // eslint-disable-next-line no-await-in-loop -- LAN must be tried before public, in order
      if (await probe(url)) {
        cachedActiveUrl = url;
        return;
      }
    }
    cachedActiveUrl = candidates[0]; // nothing reachable -- keep trying LAN, surfaces the real network error
  })().finally(() => {
    probeInFlight = null;
  });
}

export function resolveApiBaseUrl() {
  let raw = '';
  try {
    raw = import.meta.env?.VITE_API_BASE_URL || '';
  } catch {
    raw = '';
  }
  const pinned = sanitizeUrl(raw);
  if (pinned) return pinned;

  const candidates = getHoUrlCandidates();
  // Only one real address configured (LAN === public, or one field blank) --
  // nothing to fail over between, so skip probing/health-checking entirely.
  if (candidates.length < 2) return candidates[0];

  if (!cachedActiveUrl) refreshActiveUrlInBackground(candidates);
  else if (cachedActiveUrl !== candidates[0]) refreshActiveUrlInBackground(candidates); // on the fallback -- keep checking for LAN recovery
  return cachedActiveUrl || candidates[0];
}
