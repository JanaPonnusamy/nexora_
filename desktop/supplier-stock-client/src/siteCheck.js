// Website check (owner 2026-11-04): By Supplier -> Website lists the open,
// unassigned products; each is searched on the supplier's own site in the
// Sites panel, its stock read, and -- when the site has enough -- put in the
// site's cart. The grid marks it In cart / Not available; nothing is ordered
// or assigned until the operator confirms.
//
// The page* functions run INSIDE the supplier's site (webview
// executeJavaScript via siteScript), so each is self-contained -- no outer
// names -- and returns plain JSON. The rest is pure and tested.

// Type the product into the site's search box and submit it ('slow' types
// it letter by letter, to watch). 'login' = the site shows its sign-in page.
// Some admin apps (e.g. Aosta BackBone's order-entry screen) render their
// form inside an iframe, where plain document.querySelectorAll from the top
// frame finds nothing even though the field is visibly on screen -- so this
// also looks in same-origin iframes' documents (cross-origin ones throw on
// .contentDocument and are silently skipped; can't be searched anyway).
export async function pageSearch(text, slow) {
  const visible = (el) => el.getClientRects().length > 0 && !el.disabled && getComputedStyle(el).visibility !== 'hidden';
  const hay = (el) => `${el.type} ${el.name} ${el.id} ${el.placeholder} ${el.getAttribute('aria-label') || ''} ${el.className}`.toLowerCase();
  const score = (el) => (el.type === 'search' ? 4 : 0) + (/search|find|product|item|medicine|drug|keyword/.test(hay(el)) ? 3 : 0)
    - (/user|login|pass|mail|phone|mobile|otp|qty|quantity|date/.test(hay(el)) ? 8 : 0);
  const docs = [document];
  for (const f of document.querySelectorAll('iframe, frame')) {
    try { if (f.contentDocument) docs.push(f.contentDocument); } catch { /* cross-origin */ }
  }
  const inputs = docs.flatMap((d) => [...d.querySelectorAll('input')]);
  let boxes = inputs
    .filter((el) => /^(search|text|)$/i.test(el.getAttribute('type') || '') && visible(el))
    .map((el) => [el, score(el)]).filter(([, s]) => s > 0).sort((a, b) => b[1] - a[1]);
  // Older ASP-style admin sites (e.g. Aosta BackBone) often give their one
  // text box no name/placeholder/aria-label at all, so the keyword score
  // above never lifts it above 0. Fall back to the single visible, unscored
  // text/search input on the page -- if there's exactly one, it's the search
  // box (a page with several unlabeled inputs stays genuinely ambiguous).
  if (!boxes.length) {
    const bare = inputs
      .filter((el) => /^(search|text|)$/i.test(el.getAttribute('type') || '') && visible(el) && score(el) === 0);
    if (bare.length === 1) boxes = [[bare[0], 0]];
  }
  if (!boxes.length) {
    const pw = docs.flatMap((d) => [...d.querySelectorAll('input[type=password]')]);
    return { ok: false, reason: pw.some(visible) ? 'login' : 'no-search' };
  }
  const box = boxes[0][0];
  box.focus();
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  for (let i = slow ? 1 : text.length; i <= text.length; i += 1) {
    setter.call(box, text.slice(0, i));
    box.dispatchEvent(new Event('input', { bubbles: true }));
    if (slow) await new Promise((r) => { setTimeout(r, 60); });
  }
  box.dispatchEvent(new Event('change', { bubbles: true }));
  const enter = { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true, cancelable: true };
  const handled = !box.dispatchEvent(new KeyboardEvent('keydown', enter));
  box.dispatchEvent(new KeyboardEvent('keypress', enter));
  box.dispatchEvent(new KeyboardEvent('keyup', enter));
  if (handled) return { ok: true, how: 'key' };
  if (box.form) {
    if (box.form.requestSubmit) box.form.requestSubmit(); else box.form.submit();
    return { ok: true, how: 'form' };
  }
  const near = box.closest('div, section, header, nav') || document;
  const button = [...near.querySelectorAll('button, input[type=button], input[type=submit], a')].find((el) => visible(el)
    && /search|find|go/i.test(`${el.innerText || el.value || ''} ${el.title || ''} ${el.getAttribute('aria-label') || ''} ${el.className || ''}`));
  if (button) button.click();
  return { ok: true, how: button ? 'button' : 'key' };
}

// The product rows of the site's result table(s): name + stock text. Each
// row is tagged data-nexora-row=<n> so pageAdd can find it again; sig
// changes when the results do.
export function pageResults() {
  const visible = (el) => el.getClientRects().length > 0;
  const text = (el) => String((el && (el.innerText || el.textContent)) || '').replace(/\s+/g, ' ').trim();
  const docs = [document];
  for (const f of document.querySelectorAll('iframe, frame')) {
    try { if (f.contentDocument) docs.push(f.contentDocument); } catch { /* cross-origin */ }
  }
  const rows = [];
  for (const table of docs.flatMap((d) => [...d.querySelectorAll('table')])) {
    if (!visible(table)) continue;
    const all = [...table.rows];
    const head = (table.tHead && table.tHead.rows[0]) || all.find((tr) => tr.querySelector('th')) || all[0];
    if (!head) continue;
    const heads = [...head.cells].map((c) => text(c).toLowerCase());
    const nameAt = heads.findIndex((h) => /product|item|description|medicine|name/.test(h));
    const stockAt = heads.findIndex((h) => /stock|avl|avail|closing|in hand|balance/.test(h));
    if (nameAt < 0) continue;
    for (const tr of all) {
      if (tr === head || !visible(tr) || tr.cells.length <= nameAt || tr.querySelector('th')) continue;
      const n = rows.length + 1;
      tr.setAttribute('data-nexora-row', String(n));
      rows.push({ n, name: text(tr.cells[nameAt]), stock: stockAt >= 0 && tr.cells[stockAt] ? text(tr.cells[stockAt]) : '' });
    }
  }
  return { rows, sig: `${location.href}|${rows.length}|${rows.slice(0, 3).map((r) => r.name).join('|')}` };
}

// Put qty of result row n in the site's cart: its qty box, then its
// Add / Cart button.
export function pageAdd(n, qty) {
  const visible = (el) => el.getClientRects().length > 0 && !el.disabled;
  const docs = [document];
  for (const f of document.querySelectorAll('iframe, frame')) {
    try { if (f.contentDocument) docs.push(f.contentDocument); } catch { /* cross-origin */ }
  }
  let tr = null;
  for (const d of docs) { tr = d.querySelector(`[data-nexora-row="${n}"]`); if (tr) break; }
  if (!tr) return { ok: false, reason: 'gone' };
  const box = [...tr.querySelectorAll('input')].find((el) => /^(number|text|tel|)$/i.test(el.getAttribute('type') || '') && visible(el));
  if (box) {
    box.focus();
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(box, String(qty));
    box.dispatchEvent(new Event('input', { bubbles: true }));
    box.dispatchEvent(new Event('change', { bubbles: true }));
  }
  const label = (el) => `${el.innerText || el.value || ''} ${el.title || ''} ${el.getAttribute('aria-label') || ''} ${el.className || ''}`;
  const button = [...tr.querySelectorAll('button, a, input[type=button], input[type=submit]')].find((el) => visible(el) && /add|cart|buy/i.test(label(el)));
  if (!button) return { ok: false, reason: box ? 'no-add-button' : 'no-qty-box' };
  button.click();
  return { ok: true };
}

// The site's cart / checkout link, opened for the operator to place the order.
export function pageOpenCart() {
  const link = [...document.querySelectorAll('a, button')].find((el) => el.getClientRects().length > 0
    && /cart|basket|checkout/i.test(`${el.innerText || ''} ${el.title || ''} ${el.getAttribute('aria-label') || ''} ${el.getAttribute('href') || ''}`));
  if (!link) return { ok: false };
  link.click();
  return { ok: true };
}

// A page function + its arguments as the code executeJavaScript runs.
export function siteScript(fn, ...args) {
  return `(${fn.toString()})(${args.map((a) => JSON.stringify(a)).join(', ')})`;
}

// ---- matching the store's product to the site's ----

// Dosage-form words, units and pack counts ("15'S") left out; '650MG' -> '650'.
const NOISE = new Set(['TAB', 'TABS', 'TABLET', 'TABLETS', 'CAP', 'CAPS', 'CAPSULE', 'CAPSULES', 'SYP', 'SYRUP',
  'INJ', 'INJECTION', 'STRIP', 'STRIPS', 'NOS', 'S', 'X', 'MG', 'ML', 'GM', 'G', 'MCG', 'IU']);
export function siteTokens(name) {
  return String(name ?? '').toUpperCase()
    .replace(/\b\d+\s*['’`]?\s*S\b/g, ' ')
    .replace(/(\d)\s*(MG|ML|GM|G|MCG|IU)\b/g, '$1')
    .replace(/[^A-Z0-9.]+/g, ' ').replace(/(^|\s)\.+|\.+(\s|$)/g, ' ')
    .trim().split(/\s+/).filter((t) => t && !NOISE.has(t));
}

// The dosage form a name states ('' = none): a tablet is never the
// injection or syrup of the same brand + strength (XEPAN 40 TAB / INJ).
const FORMS = [
  ['TAB', /\b(TAB|TABS|TABLET|TABLETS)\b/], ['CAP', /\b(CAP|CAPS|CAPSULE|CAPSULES)\b/],
  ['INJ', /\b(INJ|INJECTION|VIAL|AMP)\b/], ['LIQ', /\b(SYP|SYRUP|SUSP|SUSPENSION|LIQUID|ORAL SOLUTION)\b/],
  ['DROP', /\b(DROP|DROPS)\b/], ['TOP', /\b(GEL|CREAM|OINT|OINTMENT|LOTION)\b/],
];
export function siteForm(name) {
  const text = String(name ?? '').toUpperCase().replace(/[^A-Z0-9]+/g, ' ');
  return (FORMS.find(([, re]) => re.test(text)) || [''])[0];
}

// 0..1. Same brand (first word) required; a different strength (first
// number) or dosage form is never the same product: DOLO 650 is not
// DOLO 1000, XEPAN 40 TAB is not XEPAN 40 INJ.
// Same brand as the first token(s): plain equality, or one side fuses the
// brand with its next token where the other keeps them separate -- a
// supplier catalog listing "BRITORVA F 10" as "BRITORVAF 10" (brand+suffix
// run together) must still match "BRITORVA F 10" from our side.
function sameBrand(a, b) {
  if (!a.length || !b.length) return false;
  if (a[0] === b[0]) return true;
  if (a.length > 1 && a[0] + a[1] === b[0]) return true;
  if (b.length > 1 && b[0] + b[1] === a[0]) return true;
  return false;
}

export function siteMatchScore(ours, theirs) {
  const a = siteTokens(ours);
  const b = siteTokens(theirs);
  if (!sameBrand(a, b)) return 0;
  const formA = siteForm(ours);
  const formB = siteForm(theirs);
  if (formA && formB && formA !== formB) return 0;
  const numA = a.find((t) => /^\d/.test(t));
  const numB = b.find((t) => /^\d/.test(t));
  if (numA && numB && Number(numA) !== Number(numB)) return 0;
  const have = new Set(b);
  return a.filter((t) => have.has(t)).length / Math.max(a.length, b.length);
}

// What to type in the site's search: brand + strength ("DOLO 650"), not the
// store's full name -- sites search by prefix, and the rest differs.
export function siteQuery(name) {
  return siteTokens(name).slice(0, 2).join(' ') || String(name ?? '').trim();
}

// "11+1" in a site's row text -> the offer.
export function siteOffer(text) {
  const m = String(text ?? '').match(/\b(\d{1,3})\s*\+\s*(\d{1,3})\b/);
  return m ? `${m[1]}+${m[2]}` : '';
}

export const SITE_MATCH_MIN = 0.5;
export function siteBestMatch(name, rows) {
  let best = null;
  for (const row of Array.isArray(rows) ? rows : []) {
    const score = siteMatchScore(name, row.name);
    if (score >= SITE_MATCH_MIN && (!best || score > best.score)) best = { row, score };
  }
  return best;
}

// Stock text -> a number: 0 for "Out of stock", Infinity for a bare
// "Available", null when the site does not say.
export function siteStock(text) {
  const t = String(text ?? '').trim();
  if (!t || /^[-–—]$/.test(t)) return null;
  if (/out of stock|not available|no stock|\bnil\b|n\/a/i.test(t)) return 0;
  const m = t.replace(/,/g, '').match(/\d+(\.\d+)?/);
  if (m) return Number(m[0]);
  if (/in stock|available|\byes\b/i.test(t)) return Infinity;
  return null;
}

// One product after its search: 'cart' (the site has the qty -> add it),
// 'partial' (fewer than wanted), 'check' (found, stock not shown) -- both
// for the operator to decide -- or 'none' (out of stock / not on the site).
export function siteDecide(qty, best) {
  if (!best) return { state: 'none', note: 'Not found on the site' };
  const stock = siteStock(best.row.stock);
  if (stock === null) return { state: 'check', note: 'Found; the site shows no stock figure' };
  if (stock <= 0) return { state: 'none', note: 'Out of stock on the site' };
  if (stock < qty) return { state: 'partial', note: `Only ${stock} in stock` };
  return { state: 'cart', note: '' };
}

// A code search is trusted on ONE result: unlike a name search (which can
// return several similar products), the supplier's own product code is
// specific, so whatever single row comes back is the product -- no
// brand/strength scoring needed. More than one row means the code search
// fell back to a name-ish match (or the code collided) -- not trusted.
export function siteBestByCode(rows) {
  const list = Array.isArray(rows) ? rows : [];
  return list.length === 1 ? { row: list[0], score: 1 } : null;
}

export const SITE_STATE_LABEL = { searching: 'Searching…', cart: 'In cart', available: 'Available', none: 'Not available', partial: 'Short stock', check: 'Check' };

// Counts for the bar; anything not decided yet is 'left'. 'available' = in
// stock on the site but not put in its cart (Add to cart switched off).
export function siteCounts(rows, marks) {
  const c = { cart: 0, available: 0, none: 0, partial: 0, check: 0, left: 0 };
  for (const r of Array.isArray(rows) ? rows : []) {
    const s = marks?.[r.key]?.state;
    if (s in c && s !== 'left') c[s] += 1;
    else c.left += 1;
  }
  return c;
}

// Outline result row n on the site (watch mode), so the operator sees which
// product the app took.
export function pageHighlight(n) {
  document.querySelectorAll('[data-nexora-hl]').forEach((el) => { el.style.outline = ''; el.removeAttribute('data-nexora-hl'); });
  const leaf = document.querySelector(`[data-nexora-row="${n}"]`);
  if (!leaf) return false;
  const row = leaf.closest('tr') || (leaf.parentElement && leaf.parentElement.closest('div.row')) || leaf;
  row.setAttribute('data-nexora-hl', '1');
  row.style.outline = '3px solid #f59e0b';
  row.style.outlineOffset = '-3px';
  row.scrollIntoView({ block: 'nearest' });
  return true;
}

// ---- RetailOrders (Wondersoft, <distributor>.retailorders.in) ----
// The distributor's New Order page (#/nav/titlecard/prodadd): the Product
// Search box (#prodSearText) drops a list -- name + "Stock : N", pack,
// manufacturer + offer (11+1), rate, MRP. Picking a product fills Packing /
// Offers; Quantity (#productQty) + ADD TO CART puts it in the cart.

export function siteKind(url) {
  let host = '';
  try { host = new URL(url).host.toLowerCase(); } catch { host = ''; }
  return /(^|\.)retailorders\.in$/.test(host) ? 'retailorders' : 'generic';
}

export async function roSearch(text, slow) {
  const visible = (el) => Boolean(el) && el.getClientRects().length > 0;
  const box = document.getElementById('prodSearText');
  if (!visible(box) || !/product/i.test(box.placeholder || '')) {
    if ([...document.querySelectorAll('input[type=password]')].some(visible)) return { ok: false, reason: 'login' };
    return { ok: false, reason: 'pick-distributor' };
  }
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  const set = (value) => {
    setter.call(box, value);
    box.dispatchEvent(new Event('input', { bubbles: true }));
    box.dispatchEvent(new KeyboardEvent('keyup', { key: value.slice(-1) || 'Backspace', bubbles: true }));
  };
  box.scrollIntoView({ block: 'nearest' });
  box.focus();
  set('');
  for (let i = slow ? 1 : text.length; i <= text.length; i += 1) {
    set(text.slice(0, i));
    if (slow) await new Promise((r) => { setTimeout(r, 70); });
  }
  return { ok: true };
}

export function roResults() {
  const visible = (el) => el.getClientRects().length > 0;
  const text = (el) => String((el && (el.innerText || el.textContent)) || '').replace(/\s+/g, ' ').trim();
  // RetailOrders has more than one result-grid skin: some list results as
  // `div.row` with the fields as children; others render a card/grid per
  // result where "Stock : N" sits on its own line. Find the result ROW
  // skin-agnostically: the smallest elements that each hold exactly one
  // "Stock : N" and a product name, then take the clickable row that wraps it.
  const STOCK = /Stock\s*:/i;
  const picks = [...document.querySelectorAll('div.row, [class*="row" i], tr, li, [role="row"]')]
    .filter((r) => visible(r) && STOCK.test(r.innerText || '')
      && (r.innerText.match(/Stock\s*:/gi) || []).length === 1 && text(r).length < 260);
  // keep the innermost match (a single result, not a wrapper of several).
  const leaf = picks.filter((r) => !picks.some((o) => o !== r && r.contains(o)));
  const rows = leaf.map((r, i) => {
    r.setAttribute('data-nexora-row', String(i + 1));
    const whole = text(r);
    // Name = text before "Stock :", also cut at an "Expiry :" marker some
    // skins put between the name and Stock (e.g. "VOZET 5 Expiry : 06/28 |
    // Stock : 13" -- without this the dangling "Expiry : 06/28 |" diluted
    // the name's token match score below threshold, so a product the site
    // genuinely has in stock showed as Not available), trimmed of a
    // trailing "(rate)" the site appends; stock = the number after "Stock :".
    const name = (whole.split(STOCK)[0] || '').split(/Expiry\s*:/i)[0].replace(/\s*\([\d.,]+\)\s*$/, '').trim();
    const stock = (whole.match(/Stock\s*:\s*([\d,]+)/i) || [])[1] || '';
    return { n: i + 1, name: name || whole, stock, info: whole.slice(0, 200) };
  });
  const box = document.getElementById('prodSearText');
  return { rows, sig: `${box ? box.value : ''}|${rows.length}|${rows.slice(0, 3).map((r) => r.name).join('|')}` };
}

// Pick result row n: the site fills Packing / Offers for it.
export async function roPick(n) {
  const leaf = document.querySelector(`[data-nexora-row="${n}"]`);
  if (!leaf) return { ok: false, reason: 'gone' };
  leaf.click();
  await new Promise((r) => { setTimeout(r, 500); });
  const val = (id) => String((document.getElementById(id) || {}).value || '').trim();
  return { ok: Boolean(val('packing') || val('offers')), packing: val('packing'), offer: val('offers') };
}

// Quantity + ADD TO CART for the picked product. The form clears itself
// once the cart takes it.
export async function roAdd(n, qty, slow) {
  const box = document.getElementById('productQty');
  const button = [...document.querySelectorAll('button')].find((b) => /ADD TO CART/i.test(b.innerText || ''));
  if (!box || !button) return { ok: false, reason: 'no-add' };
  box.focus();
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(box, String(qty));
  box.dispatchEvent(new Event('input', { bubbles: true }));
  box.dispatchEvent(new Event('change', { bubbles: true }));
  if (slow) {
    button.style.outline = '3px solid #16a34a';
    await new Promise((r) => { setTimeout(r, 700); });
    button.style.outline = '';
  }
  button.click();
  await new Promise((r) => { setTimeout(r, 900); });
  const packing = document.getElementById('packing');
  // Some products sell only in box multiples: the site then rejects the add
  // with "The order quantity should be a multiple of N" and leaves the form
  // filled. Retry once with qty rounded UP to that multiple.
  const multiple = Number((String(document.body.innerText || '').match(/quantity should be a multiple of\s*(\d+)/i) || [])[1] || 0);
  if (box.value && multiple > 1 && Number(qty) % multiple !== 0 && !roAdd.retrying) {
    const rounded = Math.ceil(Number(qty) / multiple) * multiple;
    roAdd.retrying = true;
    try {
      const again = await roAdd(n, rounded, slow);
      return { ...again, qty: rounded, note: `Site sells in multiples of ${multiple}: added ${rounded}` };
    } finally { roAdd.retrying = false; }
  }
  return { ok: true, cleared: !box.value && !(packing && packing.value) };
}

// The lines already in the cart (the grid under the form, #selgridRow_N),
// upper-cased -- so a second run never adds a product twice.
export function roCart() {
  return [...document.querySelectorAll('[id^="selgridRow_"]')].map((r) => String(r.innerText || '').replace(/\s+/g, ' ').trim().toUpperCase());
}

// Is the site's product (its result name) among the cart lines?
export function siteInCart(lines, name) {
  const want = String(name ?? '').replace(/^[.\s]+/, '').replace(/\s+/g, ' ').trim().toUpperCase();
  return Boolean(want) && Array.isArray(lines) && lines.some((line) => String(line).includes(want));
}

// ---- catalog harvest (read the supplier's whole product list with stock) ----
// RetailOrders surfaces products only through its search box, so we enumerate by
// typing short prefixes and collecting every result row. Read-only: it never
// picks or adds. Returns [{ name, stock, info }] de-duplicated by name. The
// prefixes cover the alphabet + digits; two-letter prefixes catch the long tail
// a one-letter search truncates. `onProgress(done, total, found)` is optional.
export async function roEnumerate(web, onProgress, supplierName) {
  const kind = siteKind(web.url());
  if (kind !== 'retailorders') return { ok: false, reason: 'not-retailorders', rows: [] };
  const LETTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'.split('');
  const seen = new Map();            // upper name -> row
  const prefixes = LETTERS.slice();  // start with single letters
  let done = 0;
  let entered = false;
  for (let i = 0; i < prefixes.length; i += 1) {
    const q = prefixes[i];
    const before = await web.exec(siteScript(roResults)).catch(() => null);
    let sent = await web.exec(siteScript(roSearch, q, false)).catch(() => null);
    // Not on the product-search page yet (dashboard / distributor list) --
    // try the same auto-navigation the operator would do by hand, once, then
    // retry this letter. Only reported as pick-distributor if that also fails.
    if (!entered && (sent?.reason === 'pick-distributor')) {
      entered = true;
      const enter = await web.exec(siteScript(roEnter, supplierName || '')).catch(() => null);
      if (enter?.ok) {
        await new Promise((r) => { setTimeout(r, 400); });
        sent = await web.exec(siteScript(roSearch, q, false)).catch(() => null);
      }
    }
    if (!sent?.ok) { if (sent?.reason === 'login' || sent?.reason === 'pick-distributor') return { ok: false, reason: sent.reason, rows: [] }; done += 1; continue; }
    let rows = [];
    let lastSig = '';
    let still = 0;
    for (let t = 0; t < 40; t += 1) {
      await new Promise((r) => { setTimeout(r, 250); });
      if (await web.loading()) continue;
      const res = await web.exec(siteScript(roResults)).catch(() => null);
      if (!res) continue;
      if (res.sig !== before?.sig) rows = res.rows;
      still = res.sig === lastSig ? still + 1 : 0;
      lastSig = res.sig;
      if (rows.length && still >= 4) break;
    }
    for (const r of rows) {
      const key = String(r.name || '').toUpperCase().trim();
      if (key && !seen.has(key)) seen.set(key, r);
    }
    // A full single-letter page (the site caps results) hides the rest: drill
    // into that letter with two-letter prefixes so nothing is missed.
    if (rows.length >= 50 && q.length === 1) {
      for (const c of LETTERS) prefixes.push(q + c);
    }
    done += 1;
    if (onProgress) onProgress(done, prefixes.length, seen.size);
  }
  return { ok: true, rows: [...seen.values()].map((r) => ({ name: r.name, stock: siteStock(r.stock), info: r.info })) };
}

// Parse the fields the harvest stores from a result row's full text (packing,
// rate, MRP, scheme, code). Best-effort -- name + stock are the reliable parts;
// a product code is stored when the site happens to show one (e.g. "Code:
// 12345" / "Item Code : AB12"), else left blank -- SupplierStock.code is
// nullable and the match-review's fuzzy path still covers an unmapped product.
export function harvestRow(row) {
  const info = String(row.info || '');
  const rate = (info.match(/\(([\d.,]+)\)/) || [])[1];
  const mrp = (info.match(/₹\s*([\d.,]+)/) || [])[1];
  const pack = (info.match(/\b(\d+\s*['’]?\s*S)\b/i) || [])[1];
  const code = (info.match(/\b(?:item\s*)?code\s*[:#]\s*([A-Z0-9][\w-]{0,30})/i) || [])[1];
  return { name: row.name, code: code || '', stock: row.stock, ptr: rate ? Number(String(rate).replace(/,/g, '')) : null, mrp: mrp ? Number(String(mrp).replace(/,/g, '')) : null, packing: pack || '' };
}

// ---- stock-checked auto-assign (read-only availability) ----
// One product checked on whatever site is open, WITHOUT picking or adding
// (read-only): search brand+strength then brand, match, decide. `web` is the
// WebPanel ref ({ exec, loading, url }). Used to gate Auto Assign by live
// stock on the supplier's own site.
//
// `supplierCode` (optional): this supplier's OWN product code for the item,
// already known from SupplierProductMatch (owner 2026-11-07 -- "we already
// have exact mapping ... accept supplier productcode instead of typing
// productname"). Tried FIRST and trusted on a single result (siteBestByCode);
// a code search that returns nothing crisp falls back to the existing
// name-token search below, so an unrecognized/miskeyed code never blocks the
// product -- it's just slower, same as before.
export async function siteCheckOne(web, name, qty, supplierCode) {
  const kind = siteKind(web.url());
  const search = kind === 'retailorders' ? roSearch : pageSearch;
  const results = kind === 'retailorders' ? roResults : pageResults;
  let best = null;
  const queries = [];
  if (supplierCode) queries.push({ q: String(supplierCode).trim(), byCode: true });
  for (const q of [...new Set([siteQuery(name), siteTokens(name)[0]].filter(Boolean))]) queries.push({ q, byCode: false });
  for (const { q, byCode } of queries) {
    if (!q) continue;
    const before = await web.exec(siteScript(results)).catch(() => null);
    const sent = await web.exec(siteScript(search, q, false)).catch(() => null);
    if (!sent?.ok) return { state: 'blocked', reason: sent?.reason, stock: '', match: '', offer: '' };
    let lastSig = '';
    let still = 0;
    for (let t = 0; t < 40; t += 1) {
      await new Promise((r) => { setTimeout(r, 250); });
      if (await web.loading()) continue;
      const res = await web.exec(siteScript(results)).catch(() => null);
      if (!res) continue;
      const fresh = res.sig !== before?.sig;
      best = fresh ? (byCode ? siteBestByCode(res.rows) : siteBestMatch(name, res.rows)) : null;
      if (best) break;
      still = res.sig === lastSig ? still + 1 : 0;
      lastSig = res.sig;
      if (fresh && still >= 6) break;
    }
    if (best) break;
  }
  const decision = siteDecide(qty, best);
  return { state: decision.state, note: decision.note, stock: best?.row.stock || '', match: best?.row.name || '', offer: siteOffer(best?.row.info) };
}

// Does a state mean the supplier HAS it (any stock)? 'none' = out/not found.
export function siteAvailable(state) {
  return state === 'cart' || state === 'partial' || state === 'check' || state === 'available';
}

// RetailOrders can land on either a distributor list (product search is one
// distributor in -- click the card matching the supplier) or a dashboard with
// a plain "New Order" nav link straight to #/.../prodadd (no distributor
// picking at all -- e.g. westernsalem.retailorders.in). Try both. Run in the
// page.
export function roEnter(supplierName) {
  if (/prodadd/.test(location.hash)) return { ok: true, already: true };
  const newOrderLink = [...document.querySelectorAll('a')]
    .find((a) => a.getClientRects().length && /new order/i.test(a.textContent || '') && /prodadd/.test(a.getAttribute('href') || ''));
  if (newOrderLink) { newOrderLink.click(); return { ok: true, clicked: 'New Order' }; }
  if (!/nav\/distributors/.test(location.hash)) return { ok: false, reason: 'not-distributors' };
  const norm = (s) => String(s || '').toUpperCase().replace(/[^A-Z0-9]+/g, ' ').trim();
  const want = norm(supplierName);
  const first = want.split(' ')[0];
  const cards = [...document.querySelectorAll('div, p, h5, h6, span, a')].filter((el) => el.getClientRects().length && /MEDICAL|AGENC|PHARMA|DISTRIBUTOR|SUPPL|TRADER|ENTERPRIS/i.test(el.textContent || '') && el.children.length <= 2);
  const exact = cards.find((el) => norm(el.textContent) === want);
  const byFirst = cards.find((el) => first && norm(el.textContent).split(' ')[0] === first);
  const el = exact || byFirst;
  if (!el) return { ok: false, reason: 'distributor-not-found' };
  el.click();
  return { ok: true, clicked: norm(el.textContent) };
}
