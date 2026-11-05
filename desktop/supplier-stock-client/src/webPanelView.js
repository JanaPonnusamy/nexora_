// Pure Web panel helpers (kept out of webPanel.jsx so node:test can import them).

// Address-bar text -> a loadable URL ('' when empty); a bare host gets https://.
export function webUrl(text) {
  const t = String(text ?? '').trim();
  if (!t) return '';
  return /^https?:\/\//i.test(t) ? t : `https://${t}`;
}

export function webHost(url) {
  try { return new URL(url).host.toLowerCase(); } catch { return ''; }
}

// Add sites (imported Chrome bookmarks, or one typed in) to the list: the same
// address never twice, a missing name falls back to the host.
export function webMergeSites(sites, incoming, makeId) {
  const list = Array.isArray(sites) ? sites : [];
  const have = new Set(list.map((s) => s.url));
  const added = [];
  for (const site of Array.isArray(incoming) ? incoming : []) {
    const url = webUrl(site?.url);
    if (!url || have.has(url)) continue;
    have.add(url);
    added.push({ id: makeId(), name: String(site.name ?? '').trim() || webHost(url), url });
  }
  return [...list, ...added];
}

// HO supplier portals as Sites-bar entries ('p<id>', apart from this PC's own).
export function webPortalSites(portals) {
  return (Array.isArray(portals) ? portals : []).map((p) => ({ id: `p${p.portal_id}`, name: p.name, url: p.url, portal: p }));
}

// The portal a store linked to a (unified) supplier code: the same code, or
// one sharing a member code ('107,109' <-> '107'). First in bar order wins.
export function webPortalFor(portals, supplierCode) {
  const codes = (value) => String(value ?? '').split(',').map((c) => c.trim()).filter(Boolean);
  const want = new Set(codes(supplierCode));
  if (!want.size) return null;
  return (Array.isArray(portals) ? portals : []).find((p) => codes(p.supplier_code).some((c) => want.has(c))) || null;
}

// The supplier picker's option text, and back to the supplier.
export function webSupplierOption(s) {
  return `${String(s?.supplier_name ?? '').trim()} · ${s?.supplier_code ?? ''}`;
}
export function webFindSupplier(suppliers, text) {
  const t = String(text ?? '').trim();
  return (Array.isArray(suppliers) ? suppliers : []).find((s) => webSupplierOption(s) === t) || null;
}

// A login as HO sends it -> the panel's shape (never a password).
export function webLogin(login) {
  return login ? { username: login.username || '', hasPassword: Boolean(login.has_password), autoSubmit: Boolean(login.auto_submit) } : null;
}

// Move a site one place up (-1) or down (+1) in the bar.
export function webMoveSite(sites, id, dir) {
  const i = sites.findIndex((s) => s.id === id);
  const j = i + dir;
  if (i < 0 || j < 0 || j >= sites.length) return sites;
  const next = [...sites];
  [next[i], next[j]] = [next[j], next[i]];
  return next;
}
