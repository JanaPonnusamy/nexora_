'use strict';

// Explicit IPC allowlist. Every channel the preload bridge exposes must be
// listed here; main.cjs refuses to register a handler for anything not in
// this list, and preload refuses to invoke anything not in this list.
// This is the "no arbitrary renderer-to-main execution" control from
// Phase 2 §6 — enforced structurally, not just by convention.
const IPC_CHANNELS = Object.freeze({
  APP_GET_VERSION: 'app:getVersion',
  APP_GET_PLATFORM_INFO: 'app:getPlatformInfo',
  THEME_GET_NATIVE: 'theme:getNative',
  THEME_SET_PREFERENCE: 'theme:setPreference',
  HEALTH_CHECK: 'app:healthCheck',
  SESSION_GET: 'session:get',
  SESSION_SET: 'session:set',
  SESSION_CLEAR: 'session:clear',
  // UI-state persistence (Order Workspace/Procurement export settings, etc.)
  // — a separate per-name JSON file store, distinct from the SESSION_* login
  // vault above. Ported verbatim from supplier-stock-client's session:read/
  // write/path so OwExportKit.js (owDefaultExportSettings et al.) works
  // unmodified via window.nexoraDesktop.
  UI_SESSION_PATH: 'session:path',
  UI_SESSION_READ: 'session:read',
  UI_SESSION_WRITE: 'session:write',
  // Order Workspace export-to-disk (Excel/CSV written straight to a chosen
  // folder), ported verbatim from supplier-stock-client's export:*.
  EXPORT_WRITE_FILE: 'export:writeFile',
  EXPORT_OPEN_PATH: 'export:openPath',
  EXPORT_CHOOSE_FOLDER: 'export:chooseFolder',
  // Store-side copy of a store's HO order cache (one JSON file per store),
  // ported from supplier-stock-client's orderCache:read/write.
  ORDER_CACHE_READ: 'orderCache:read',
  ORDER_CACHE_WRITE: 'orderCache:write',
});

module.exports = { IPC_CHANNELS };
