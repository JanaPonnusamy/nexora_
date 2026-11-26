// Sidebar collapse + per-group open/closed persistence. Namespaced distinctly
// from settingsStore's `nextechMediq.settings` key (and from either of the
// other two desktop apps' own storage) so this app's sidebar preference
// never collides with anything else on the same machine.
const STORAGE_KEY = 'nextechMediq.sidebar';

function readRaw() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch {
    return null;
  }
}

function writeRaw(next) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {
    // Best-effort only — a private/cleared profile must not crash the shell.
  }
}

export function loadCollapsed() {
  const stored = readRaw();
  return Boolean(stored?.collapsed);
}

export function saveCollapsed(collapsed) {
  const stored = readRaw() || {};
  writeRaw({ ...stored, collapsed: Boolean(collapsed) });
}

// Returns the persisted open/closed map, or null when nothing is stored yet
// (caller falls back to "all open" for every known group).
export function loadOpenGroups() {
  const stored = readRaw();
  return stored?.openGroups && typeof stored.openGroups === 'object' ? stored.openGroups : null;
}

export function saveOpenGroups(openGroups) {
  const stored = readRaw() || {};
  writeRaw({ ...stored, openGroups });
}

export const SIDEBAR_STORAGE_KEY = STORAGE_KEY;
