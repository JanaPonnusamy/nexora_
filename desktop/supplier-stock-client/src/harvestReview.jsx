import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from './api/client.js';
import { harvestRow, roEnumerate, siteScript } from './siteCheck.js';

const HARVEST_RETRIES = 3;     // owner: auto-retry N times, then keep old stock
const sleep = (ms) => new Promise((r) => { setTimeout(r, ms); });

// How long a harvest takes, averaged over recent runs on THIS PC (that is where
// the catalog is read, so the timing is this PC's). Kept as a short rolling list
// in localStorage; shown so the operator knows roughly how long to wait.
const TIMING_KEY = 'nexora.desktop.harvestTimings';
const TIMING_KEEP = 8;
function readTimings() {
  try { const v = JSON.parse(localStorage.getItem(TIMING_KEY) || '[]'); return Array.isArray(v) ? v.filter((n) => Number.isFinite(n) && n > 0) : []; }
  catch { return []; }
}
function pushTiming(ms) {
  try {
    const next = [...readTimings(), Math.round(ms)].slice(-TIMING_KEEP);
    localStorage.setItem(TIMING_KEY, JSON.stringify(next));
    return next;
  } catch { return readTimings(); }
}
function avgOf(list) { return list.length ? Math.round(list.reduce((a, b) => a + b, 0) / list.length) : 0; }
// "~45s" / "~1m 20s" from milliseconds.
export function fmtDur(ms) {
  if (!ms || ms < 0) return '';
  const s = Math.round(ms / 1000);
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;
}

// Three separate concerns, kept apart (owner 2026-11-05):
//  * useHarvest  -- read the supplier's whole catalog from its open portal and
//    write it to SupplierStock. Nothing else. Live Stock mode then shows it.
//  * useMatchReview + MatchReview -- the "Map supplier products" panel: match the
//    harvested stock to the store's products and save confirmed maps to
//    SupplierProductMatch (so unmapped products become visible in Live Stock).
// Adding to the site's cart is the existing Website site-check flow, not here.

// --- Harvest: read the WHOLE site catalog -> SupplierStock -------------------
// Atomic + resilient (owner 2026-11-05): read the ENTIRE catalog, then post once
// with complete=true so the server swaps SupplierStock all-or-nothing. If a read
// breaks mid-way, retry up to N times; if all fail, the old stock is kept
// untouched (we never post a partial list). Also auto-runs when the selected
// supplier's stock is stale (older than today's order).
export function useHarvest({ webRef, store, supplierCode, supplierName, session, orderAt }) {
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState('');
  const [result, setResult] = useState(null);   // { stored } | null
  const [error, setError] = useState('');
  const [avgMs, setAvgMs] = useState(() => avgOf(readTimings()));   // rolling avg on this PC
  const [lastMs, setLastMs] = useState(0);        // the most recent run's duration
  const autoTried = useRef('');                  // store|supplier we've auto-run for

  // One full-catalog read; throws on a broken/partial read so the caller retries.
  const readCatalog = useCallback(async () => {
    const web = webRef.current;
    if (!web?.ready()) { const e = new Error('site-not-open'); e.soft = 'Open the supplier’s site first.'; throw e; }
    const out = await web.exec(siteScript(roEnumerate, undefined, supplierName || '')).catch(() => null);
    if (!out) throw new Error('read-failed');       // exec died mid-way -> retry
    if (!out.ok) {
      const e = new Error(out.reason || 'read-failed');
      e.soft = out.reason === 'login' ? 'Sign in to the supplier’s site first.'
        : out.reason === 'pick-distributor' ? 'Open New Order for this distributor on the site, then try again.'
          : 'Could not read the supplier’s product list.';
      e.stop = out.reason === 'login' || out.reason === 'pick-distributor';  // don't retry these
      throw e;
    }
    if (!out.rows?.length) throw new Error('empty');  // nothing read -> retry
    return out.rows.map(harvestRow);
  }, [webRef]);

  const harvest = useCallback(async ({ silent = false } = {}) => {
    if (!store || !supplierCode || busy) return false;
    setError(''); setResult(null); setBusy(true);
    const startedAt = Date.now();
    const eta = avgMs ? ` (usually ~${fmtDur(avgMs)})` : '';
    try {
      let rows = null;
      for (let attempt = 1; attempt <= HARVEST_RETRIES; attempt += 1) {
        try {
          if (!silent) setProgress(`Reading the supplier’s product list…${attempt > 1 ? ` (retry ${attempt - 1})` : eta}`);
          rows = await readCatalog();
          break;
        } catch (e) {
          if (e.stop) { setError(e.soft || 'Could not read the catalog.'); return false; }  // keep old stock, no retry
          if (attempt >= HARVEST_RETRIES) {
            // All retries failed -> keep the OLD stock untouched (never posted a partial).
            setError((e.soft || 'Could not read the full catalog') + ' — kept the existing stock.');
            return false;
          }
          await sleep(1500 * attempt);  // backoff before the next try
        }
      }
      // Only now, with a COMPLETE read, post it (server swaps atomically).
      if (!silent) setProgress(`Saving ${rows.length} products to stock…`);
      const r = await api.legacyHarvestSupplierStock(store, supplierCode, rows, true, session);
      const took = Date.now() - startedAt;
      setLastMs(took);
      setAvgMs(avgOf(pushTiming(took)));
      setResult(r);
      setProgress(`Saved ${r.stored} products in ${fmtDur(took)}. Live Stock now shows this supplier’s stock.`);
      return true;
    } catch (e) {
      // A POST failure also keeps the old stock (the server rolled back).
      setError((e.message || 'Harvest failed') + ' — kept the existing stock.');
      return false;
    } finally {
      setBusy(false);
    }
  }, [store, supplierCode, session, busy, readCatalog]);

  // Auto-harvest when this supplier's stock is stale vs. today's order. Runs
  // once per (store, supplier) selection, silently, in the background.
  useEffect(() => {
    if (!store || !supplierCode || !orderAt) return;
    const key = `${store}|${supplierCode}`;
    if (autoTried.current === key) return;
    let cancelled = false;
    (async () => {
      try {
        const st = await api.legacySupplierHarvestStatus(store, supplierCode, session);
        if (cancelled) return;
        const fresh = st?.harvested_at && new Date(st.harvested_at) >= new Date(orderAt);
        autoTried.current = key;
        if (!fresh) {
          // Give the site a moment to finish auto sign-in before reading.
          await sleep(2500);
          if (!cancelled) harvest({ silent: true });
        }
      } catch { autoTried.current = key; }
    })();
    return () => { cancelled = true; };
  }, [store, supplierCode, orderAt, session, harvest]);

  return { busy, progress, result, error, harvest, setError, avgMs, lastMs };
}

// --- Map review: match SupplierStock -> store products, save confirmed maps ---
export function useMatchReview({ store, supplierCode, session }) {
  const [busy, setBusy] = useState(false);
  const [review, setReview] = useState(null);     // { counts, items }
  const [error, setError] = useState('');
  const loadedFor = useRef('');

  const load = useCallback(async () => {
    if (!store || !supplierCode) return;
    setError(''); setBusy(true);
    try {
      const r = await api.legacySupplierMatchReview(store, supplierCode, session);
      setReview(r); loadedFor.current = `${store}|${supplierCode}`;
    } catch (e) { setError(e.message || 'Could not load the match review.'); }
    finally { setBusy(false); }
  }, [store, supplierCode, session]);

  const confirm = useCallback(async (item, productCode) => {
    try {
      await api.legacyConfirmSupplierMatch(store, supplierCode, {
        supplier_product_code: item.supplier_code, supplier_product_name: item.supplier_name,
        product_code: productCode || '',
      }, session);
      await load();
    } catch (e) { setError(e.message || 'Could not save that mapping.'); }
  }, [store, supplierCode, session, load]);

  return { busy, review, error, load, confirm, setError };
}

// The "Map supplier products" panel: three tiers, each its own colour +
// watermark. Confirm a suggestion or map an unmapped product once.
export function MatchReview({ review, storeProducts, onConfirm, busy }) {
  const [tab, setTab] = useState('suggested');
  if (!review) return null;
  const items = review.items.filter((m) => m.tier === tab);
  const c = review.counts;
  return (
    <div className="hv" role="region" aria-label="Map supplier products">
      <div className="hv-head">
        <div className="hv-tabs" role="tablist">
          <button type="button" role="tab" aria-selected={tab === 'matched'} className={`hv-tab hv-tab--matched${tab === 'matched' ? ' is-on' : ''}`} onClick={() => setTab('matched')}>Matched {c.matched}</button>
          <button type="button" role="tab" aria-selected={tab === 'suggested'} className={`hv-tab hv-tab--suggested${tab === 'suggested' ? ' is-on' : ''}`} onClick={() => setTab('suggested')}>To confirm {c.suggested}</button>
          <button type="button" role="tab" aria-selected={tab === 'needs_mapping'} className={`hv-tab hv-tab--unmapped${tab === 'needs_mapping' ? ' is-on' : ''}`} onClick={() => setTab('needs_mapping')}>To map {c.needs_mapping}</button>
        </div>
      </div>
      <div className="hv-list">
        <table className="ow-fixed hv-table">
          <thead><tr><th>Supplier product</th><th className="ow-num">Stock</th><th>Store product</th><th /></tr></thead>
          <tbody>
            {items.slice(0, 200).map((m) => (
              <tr key={m.supplier_code} className={`hv-row hv-row--${m.tier}`}>
                <td title={m.supplier_name}><span className={`hv-dot hv-dot--${m.tier}`} /> {m.supplier_name}</td>
                <td className="ow-num">{m.stock}</td>
                <td>
                  {m.tier === 'needs_mapping'
                    ? <MapPicker products={storeProducts} onPick={(code) => onConfirm(m, code)} />
                    : <span title={`${m.method} · ${m.confidence}%`}>{m.product_name || '—'}</span>}
                </td>
                <td>
                  {m.tier === 'suggested' && (
                    <span className="hv-acts">
                      <button type="button" className="ow-btn ow-btn-sm" disabled={busy} title="Confirm this match" onClick={() => onConfirm(m, m.product_code)}>✓</button>
                      <button type="button" className="ow-btn ow-btn-sm" disabled={busy} title="Wrong — map it" onClick={() => onConfirm(m, '')}>✕</button>
                    </span>
                  )}
                  {m.tier === 'matched' && <span className="hv-ok" title={`${m.method} · ${m.confidence}%`}>✓</span>}
                </td>
              </tr>
            ))}
            {!items.length && <tr><td colSpan={4} className="ow-empty">Nothing in this group.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// Type-to-find the store product for an unmapped supplier product.
function MapPicker({ products, onPick }) {
  const [text, setText] = useState('');
  const list = Array.isArray(products) ? products : [];
  const hit = list.find((s) => `${s.product_name} · ${s.product_code}` === text);
  return (
    <span className="hv-map">
      <input list="hv-product-options" value={text} placeholder="Find store product…" onChange={(e) => setText(e.target.value)} />
      <button type="button" className="ow-btn ow-btn-sm" disabled={!hit} onClick={() => hit && onPick(hit.product_code)}>Map</button>
      <datalist id="hv-product-options">
        {list.slice(0, 1000).map((s) => <option key={s.product_code} value={`${s.product_name} · ${s.product_code}`} />)}
      </datalist>
    </span>
  );
}
