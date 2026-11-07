// Pure Device Controller enrollment decisions. The Electron main process
// still does the filesystem and HTTP work; these answers are what the
// handler uses so a missing login or an unchanged key never calls HO.

function enrollmentPlan({ apiBaseUrl, token, storedMarker, nextMarker }) {
  if (!apiBaseUrl || !token) return { action: 'skip', ok: false, reason: 'not signed in' };
  if (storedMarker && nextMarker && storedMarker === nextMarker) return { action: 'skip', ok: true, skipped: true };
  return { action: 'register' };
}

module.exports = { enrollmentPlan };
