'use strict';

// Hard security floor for every BrowserWindow this app creates.
// Per Phase 2 §6: contextIsolation true, nodeIntegration false, no renderer
// Node access, sandboxed by default (quick-stock-client's tighter posture,
// not supplier-stock-client's sandbox:false — NexTech MediQ Workspace has no webview
// requirement yet, so there is no reason to loosen this).
function secureWebPreferences(preloadPath) {
  return {
    preload: preloadPath,
    contextIsolation: true,
    nodeIntegration: false,
    sandbox: true,
    webSecurity: true,
    allowRunningInsecureContent: false,
    navigateOnDragDrop: false,
  };
}

// Allowlist for renderer navigation / window.open — nothing arbitrary.
// Extended in later phases only for specific, named, authorized hosts.
const NAVIGATION_ALLOWLIST = [];

function isNavigationAllowed(targetUrl) {
  try {
    const url = new URL(targetUrl);
    if (url.protocol === 'file:') return true;
    return NAVIGATION_ALLOWLIST.some((allowed) => url.origin === allowed);
  } catch {
    return false;
  }
}

module.exports = { secureWebPreferences, isNavigationAllowed, NAVIGATION_ALLOWLIST };
