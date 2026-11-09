import { useCallback, useEffect, useRef, useState } from 'react';
import {
  pageAdd, pageHighlight, pageOpenCart, pageResults, pageSearch, roAdd, roCart, roPick, roResults, roSearch,
  SITE_STATE_LABEL, siteBestByCode, siteBestMatch, siteCounts, siteDecide, siteInCart, siteKind, siteOffer, siteQuery, siteScript, siteTokens,
  roEnter,
} from './siteCheck.js';

// By Supplier -> Website: checks the listed products on the supplier's site
// in the Sites panel (webRef = WebPanel's handle), one at a time in grid
// order. Marks live here until the list changes (resetKey); the order
// itself only changes when the operator confirms (onConfirm assigns).

const sleep = (ms) => new Promise((resolve) => { setTimeout(resolve, ms); });
const ADD_KEY = 'nexora.desktop.siteAddToCart';
const WATCH_KEY = 'nexora.desktop.siteWatch';
// How each kind of site searches, lists, picks, adds and shows its cart
// (siteCheck.js).
const ADAPTERS = {
  generic: { search: pageSearch, results: pageResults, pick: null, add: pageAdd, cart: null },
  retailorders: { search: roSearch, results: roResults, pick: roPick, add: roAdd, cart: roCart },
};
const STOP_TEXT = {
  login: 'Sign in to the site first — it is showing its login page.',
  'pick-distributor': 'On the site open New Order for this distributor (its Product Search page), then press Continue.',
};
const loadFlag = (key, fallback) => { try { const v = localStorage.getItem(key); return v == null ? fallback : v !== 'false'; } catch { return fallback; } };
const saveFlag = (key, value) => { try { localStorage.setItem(key, String(value)); } catch { /* per PC */ } };

export function useSiteCheck({ webRef, rows, qtyOf, nameOf, codeOf, resetKey, onStep, siteUrl, supplierName }) {
  const [marks, setMarks] = useState({});
  const [running, setRunning] = useState(false);
  const [note, setNote] = useState('');
  const [status, setStatus] = useState('');
  // Off = search and read stock only: in-stock products are marked Available
  // and the site's cart is left alone.
  const [addToCart, setAddToCart] = useState(() => loadFlag(ADD_KEY, true));
  // Watch = type letter by letter, outline the match, pause on each step.
  const [watch, setWatch] = useState(() => loadFlag(WATCH_KEY, true));
  const live = useRef({});
  live.current = { marks, rows, addToCart, watch, onStep };
  const runRef = useRef(false);
  useEffect(() => { saveFlag(ADD_KEY, addToCart); }, [addToCart]);
  useEffect(() => { saveFlag(WATCH_KEY, watch); }, [watch]);
  useEffect(() => { runRef.current = false; setMarks({}); setNote(''); setStatus(''); }, [resetKey]);
  const mark = useCallback((key, value) => setMarks((cur) => {
    const next = { ...cur };
    if (value) next[key] = value; else delete next[key];
    return next;
  }), []);

  // Search one product: by its known supplier product code first (owner
  // 2026-11-07 -- SupplierProductMatch already has the exact mapping, so
  // search by code instead of typing the name when we have it), then brand +
  // strength, then the brand alone (some sites find "EMCLOBAL" but nothing
  // for "EMCLOBAL CREAM"). Each search waits for a matching result, or the
  // results to settle without one (~1.5s unchanged), or ~10s.
  async function search(row, tag) {
    const web = webRef.current;
    if (!web?.ready()) return { stop: 'Open the supplier’s site on the right first (🌐 Sites).' };
    const site = ADAPTERS[siteKind(web.url())];
    const slow = live.current.watch;
    const name = nameOf(row);
    const code = codeOf ? codeOf(row) : '';
    let best = null;
    const queries = [];
    if (code) queries.push({ query: String(code).trim(), byCode: true });
    for (const query of [...new Set([siteQuery(name), siteTokens(name)[0]].filter(Boolean))]) queries.push({ query, byCode: false });
    for (const { query, byCode } of queries) {
      if (!query) continue;
      setStatus(`${tag}${name} — searching “${query}”…`);
      const before = await web.exec(siteScript(site.results)).catch(() => null);
      let sent = await web.exec(siteScript(site.search, query, false)).catch(() => null);
      // RetailOrders: on the distributor list (or elsewhere) -> pick this
      // supplier's distributor, wait for its Product Search, retry once.
      if (sent?.reason === 'pick-distributor' && supplierName) {
        setStatus(`${tag}opening ${supplierName} on the site…`);
        if (await enterDistributor(web)) sent = await web.exec(siteScript(site.search, query, false)).catch(() => null);
      }
      if (!sent?.ok) return { stop: STOP_TEXT[sent?.reason] || 'No product search box found on this page of the site.' };
      let lastSig = '';
      let still = 0;
      // Quick mode polls faster and settles sooner (~0.6s unchanged).
      for (let t = 0; t < (slow ? 40 : 60); t += 1) {
        await sleep(150);
        if (web.loading()) continue;
        const res = await web.exec(siteScript(site.results)).catch(() => null);
        if (!res) continue;
        const fresh = res.sig !== before?.sig;
        best = fresh ? (byCode ? siteBestByCode(res.rows) : siteBestMatch(name, res.rows)) : null;
        if (best) break;
        still = res.sig === lastSig ? still + 1 : 0;
        lastSig = res.sig;
        if (fresh && still >= 3) break;
      }
      if (best) break;
    }
    if (best && slow) {
      await web.exec(siteScript(pageHighlight, best.row.n)).catch(() => null);
      await sleep(400);
    }
    return { site, best, slow };
  }

  async function checkOne(row, tag) {
    const found = await search(row, tag);
    if (found.stop) return found;
    const { site, best, slow } = found;
    const web = webRef.current;
    const decision = siteDecide(qtyOf(row), best);
    let picked = null;
    if (best && site.pick && decision.state !== 'none') picked = await web.exec(siteScript(site.pick, best.row.n, slow)).catch(() => null);
    const result = {
      ...decision, match: best?.row.name || '', stock: best?.row.stock || '',
      offer: picked?.offer && !/no offer/i.test(picked.offer) ? picked.offer : siteOffer(best?.row.info),
    };
    const seen = best ? `${best.row.name} · Stock ${best.row.stock || '—'}${result.offer ? ` · Offer ${result.offer}` : ''}` : 'not on the site';
    const done = (value) => {
      setStatus(`${tag}${nameOf(row)} → ${seen} → ${SITE_STATE_LABEL[value.state]}${value.note && value.state !== 'none' ? ` (${value.note})` : ''}`);
      return { mark: value };
    };
    if (decision.state !== 'cart') return done(result);
    // Already in the site's cart (an earlier run): never added twice, and
    // shown as In cart even with adding switched off.
    const cartBefore = site.cart ? await web.exec(siteScript(site.cart)).catch(() => null) : null;
    if (siteInCart(cartBefore, best.row.name)) return done({ ...result, note: 'Already in the site’s cart — not added again' });
    if (!live.current.addToCart) return done({ ...result, state: 'available', note: 'In stock on the site; not put in its cart' });
    if (site.pick && !picked?.ok) return done({ ...result, state: 'check', note: 'Found, but the site did not take the pick' });
    setStatus(`${tag}${nameOf(row)} → ${seen} → adding ${qtyOf(row)} to the cart…`);
    const added = await web.exec(siteScript(site.add, best.row.n, qtyOf(row), slow)).catch(() => null);
    if (!added?.ok) return done({ ...result, state: 'check', note: 'Found, but the app could not add it to the cart' });
    if (site.cart) {
      const cartAfter = await web.exec(siteScript(site.cart)).catch(() => null);
      if (!siteInCart(cartAfter, best.row.name)) return done({ ...result, state: 'check', note: 'Add to cart pressed, but it is not in the site’s cart — check it' });
    } else if (added.cleared === false) return done({ ...result, state: 'check', note: 'Add to cart pressed — check the site’s cart' });
    return done({ ...result, note: added.note || 'Added to the site’s cart' });
  }

  // The panel may be showing another tab (e.g. a local site): go to the
  // supplier's own portal first -- its saved login signs in by itself.
  async function openSupplierSite() {
    const web = webRef.current;
    if (!siteUrl || !web) return;
    const host = (u) => { try { return new URL(u).host; } catch { return ''; } };
    if (host(web.url()) === host(siteUrl)) return;
    web.openUrl(siteUrl);
    for (let t = 0; t < 40; t += 1) {
      await sleep(250);
      if (web.ready() && !web.loading() && host(web.url()) === host(siteUrl)) break;
    }
    await sleep(1500); // auto sign-in
  }

  async function enterDistributor(web) {
    const hashOf = () => { try { return new URL(web.url()).hash; } catch { return ''; } };
    if (!/nav\/distributors/.test(hashOf())) {
      await web.exec('location.hash = "#/nav/distributors"').catch(() => null);
      await sleep(1500);
    }
    for (let t = 0; t < 10; t += 1) {
      const r = await web.exec(siteScript(roEnter, supplierName)).catch(() => null);
      if (r?.ok) break;
      await sleep(500);
    }
    for (let t = 0; t < 40; t += 1) {
      await sleep(250);
      const ok = await web.exec('(() => { const b = document.getElementById("prodSearText"); return Boolean(b && b.getClientRects().length); })()').catch(() => false);
      if (ok) return true;
    }
    return false;
  }

  async function start() {
    if (runRef.current) return;
    runRef.current = true;
    setRunning(true);
    setNote('');
    try {
      await openSupplierSite();
      const list = live.current.rows;
      for (let i = 0; i < list.length; i += 1) {
        const row = list[i];
        if (!runRef.current) break;
        if (live.current.marks[row.key]) continue;
        live.current.onStep?.(row);
        mark(row.key, { state: 'searching' });
        const out = await checkOne(row, `${i + 1}/${list.length} · `);
        if (out.stop) { mark(row.key, null); setNote(out.stop); break; }
        mark(row.key, out.mark);
        await sleep(live.current.watch ? 700 : 60);
      }
    } finally {
      runRef.current = false;
      setRunning(false);
    }
  }

  // Product by product: check just this row on the site and mark it.
  async function checkRow(row) {
    if (runRef.current) return;
    runRef.current = true;
    setRunning(true);
    setNote('');
    try {
      live.current.onStep?.(row);
      const prev = live.current.marks[row.key];
      mark(row.key, { state: 'searching' });
      const out = await checkOne(row, '');
      if (out.stop) { mark(row.key, prev || null); setNote(out.stop); } else mark(row.key, out.mark);
    } finally {
      runRef.current = false;
      setRunning(false);
    }
  }

  // Bulk call by the operator: every product not decided yet (or every
  // product, all=true) marked Available / Not available in one go.
  function markRest(state, all = false) {
    setMarks((cur) => {
      const next = { ...cur };
      for (const r of live.current.rows) {
        const m = cur[r.key];
        if (m?.state === 'searching') continue;
        if (!all && m && m.state !== 'partial' && m.state !== 'check') continue;
        next[r.key] = { ...(m || {}), state, note: 'Marked by you (bulk)' };
      }
      return next;
    });
  }

  return {
    marks, running, note, status, counts: siteCounts(rows, marks), mark, addToCart, setAddToCart, watch, setWatch,
    start, checkRow, markRest, stop: () => { runRef.current = false; },
    // Show one product on the site without deciding anything.
    show: (row) => { if (!runRef.current) search(row, '').then((out) => setNote(out.stop || '')); },
    openCart: () => webRef.current?.exec(siteScript(pageOpenCart)).then((r) => { if (!r?.ok) setNote('No cart link found on this page — open the cart on the site.'); })
      .catch(() => setNote('Open the supplier’s site first.')),
    reset: () => { runRef.current = false; setMarks({}); setNote(''); setStatus(''); },
  };
}

// The grid's per-row result: a chip (click = show it on the site) and the
// operator's own call when the app could not decide.
export function SiteMark({ site, row, disabled }) {
  const m = site.marks[row.key];
  const title = m
    ? [SITE_STATE_LABEL[m.state], m.match && `Site: ${m.match}`, m.stock && `Stock: ${m.stock}`, m.offer && `Offer: ${m.offer}`, m.note].filter(Boolean).join(' · ')
    : 'Not checked yet — click to check it on the site and mark it';
  return (
    <span className="pw-site-mark">
      <button type="button" className={`pw-site-chip pw-site-chip--${m?.state || 'todo'}`} title={title} disabled={site.running}
        onClick={(e) => { e.stopPropagation(); if (m) site.show(row); else site.checkRow(row); }}>
        {m ? SITE_STATE_LABEL[m.state] : 'Check'}{m?.stock && m.state !== 'searching' ? ` · ${m.stock}` : ''}
      </button>
      {m?.state !== 'searching' && !disabled && !site.running && (
        <>
          {m && <button type="button" className="pw-icon-act" title="Check this product on the site again" aria-label="Re-check"
            onClick={(e) => { e.stopPropagation(); site.checkRow(row); }}>↻</button>}
          {m?.state !== 'cart' && m?.state !== 'available' && <button type="button" className="pw-icon-act pw-icon-act--ok" title="Available (I checked / put it in the site’s cart)" aria-label="Mark available"
            onClick={(e) => { e.stopPropagation(); site.mark(row.key, { ...(m || {}), state: site.addToCart ? 'cart' : 'available', note: 'Marked by you' }); }}>✓</button>}
          {m?.state !== 'none' && <button type="button" className="pw-icon-act pw-icon-act--no" title="Not available on the site" aria-label="Mark not available"
            onClick={(e) => { e.stopPropagation(); site.mark(row.key, { ...(m || {}), state: 'none', note: 'Marked by you' }); }}>✕</button>}
        </>
      )}
    </span>
  );
}

// Run / pause, the counts, and -- once every product is decided -- the
// confirm step. Confirm only ASSIGNS the In-cart / Available products in
// the order; placing the order on the site stays with the operator.
export function SiteCheckBar({ site, total, siteName, supplierName, busy, onConfirm, extra }) {
  const [confirming, setConfirming] = useState(false);
  const { counts } = site;
  const done = total > 0 && counts.left === 0;
  const askYou = counts.partial + counts.check;
  const toOrder = counts.cart + counts.available;
  useEffect(() => { if (!done) setConfirming(false); }, [done]);
  return (
    <div className="pw-sitebar" role="region" aria-label="Website check">
      <span className="pw-sitebar-site" title={siteName ? `Checking on ${siteName}` : 'Link this supplier to its website in 🌐 Sites → ⚙'}>
        🌐 {siteName || 'No website linked'}
      </span>
      {site.running
        ? <button type="button" className="ow-btn ow-btn-sm" onClick={site.stop}>⏸ Pause</button>
        : <button type="button" className="ow-btn ow-btn-sm ow-btn-primary" disabled={!total || done || busy} onClick={site.start}>
          ▶ {counts.left < total ? 'Continue' : 'Check on site'}</button>}
      {extra}
      {!site.running && counts.left + askYou > 0 && (
        <span className="pw-sitebar-bulk" role="group" aria-label="Bulk mark">
          <button type="button" className="ow-btn ow-btn-sm pw-bulk-ok" disabled={busy}
            title="Mark every product not decided yet (and Short stock / Check) as Available"
            onClick={() => site.markRest(site.addToCart ? 'cart' : 'available')}>✓ Rest available</button>
          <button type="button" className="ow-btn ow-btn-sm pw-bulk-no" disabled={busy}
            title="Mark every product not decided yet (and Short stock / Check) as Not available"
            onClick={() => site.markRest('none')}>✕ Rest not available</button>
        </span>
      )}
      <label className="pw-sitebar-opt" title="Type each product, outline the match and pause on every step, so you can follow it">
        <input type="checkbox" checked={site.watch} onChange={(e) => site.setWatch(e.target.checked)} /> Show each step (off = quick)
      </label>
      <label className="pw-sitebar-opt" title="Off: search and read stock only — nothing is put in the site's cart">
        <input type="checkbox" checked={site.addToCart} disabled={site.running} onChange={(e) => site.setAddToCart(e.target.checked)} /> Add to the site’s cart
      </label>
      <span className="pw-sitebar-counts">
        <span className="pw-site-chip pw-site-chip--cart">In cart {counts.cart}</span>
        {counts.available > 0 && <span className="pw-site-chip pw-site-chip--available">Available {counts.available}</span>}
        <span className="pw-site-chip pw-site-chip--none">Not available {counts.none}</span>
        {askYou > 0 && <span className="pw-site-chip pw-site-chip--check">Check {askYou}</span>}
        <span className="pw-sitebar-left">{counts.left} left</span>
      </span>
      {done && !confirming && (
        <button type="button" className="ow-btn ow-btn-sm" disabled={busy} onClick={() => setConfirming(true)}>Review &amp; confirm…</button>
      )}
      {(done || counts.left < total) && !site.running && (
        <button type="button" className="ow-btn ow-btn-sm" disabled={busy} onClick={site.reset} title="Clear the marks and check again">Start over</button>
      )}
      {(site.status || site.note) && (
        <span className="pw-sitebar-status" role="status" title={site.note || site.status}>
          {site.note ? <b className="pw-sitebar-note">{site.note}</b> : site.status}
        </span>
      )}
      {confirming && (
        <div className="pw-sitebar-confirm" role="alertdialog" aria-label="Confirm the website order">
          <span>
            {counts.cart} product{counts.cart === 1 ? '' : 's'} in {siteName || 'the site'}’s cart{counts.available ? `, ${counts.available} available (add them on the site)` : ''}{askYou ? `; ${askYou} still need your call (✓ / ✕)` : ''}.
            {' '}Place the order on the site, then confirm to assign {toOrder === 1 ? 'it' : 'them'} to {supplierName} in this order.
            {counts.none ? ` ${counts.none} not available stay open for the next supplier.` : ''}
          </span>
          <button type="button" className="ow-btn ow-btn-sm" onClick={site.openCart}>Open site cart</button>
          <button type="button" className="ow-btn ow-btn-sm ow-btn-primary" disabled={busy || !toOrder || askYou > 0}
            onClick={() => onConfirm().then((ok) => ok && setConfirming(false))}>
            Confirm — assign {toOrder} to {supplierName}
          </button>
          <button type="button" className="ow-btn ow-btn-sm" onClick={() => setConfirming(false)}>Not yet</button>
        </div>
      )}
    </div>
  );
}
