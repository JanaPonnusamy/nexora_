// Ported verbatim from desktop/supplier-stock-client/src/harvestReview.jsx
// (owner instruction: copy logic unchanged, only adapt API plumbing/theme).
// Only change: api.legacy*(…, session) calls -> direct service imports with
// session dropped. The harvest/confirm-match writes this file makes are
// gated from the parent (ProcurementWorkspace), not altered here.
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  legacyHarvestSupplierStock,
  legacySupplierHarvestStatus,
  legacySupplierMatchReview,
  legacyConfirmSupplierMatch,
} from '../../services/legacyOrderService.js';
import { harvestRow, roEnumerate, siteScript } from './siteCheck.js';

const HARVEST_RETRIES = 3;
const sleep = (ms) => new Promise((r) => { setTimeout(r, ms); });

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
export function fmtDur(ms) {
  if (!ms || ms < 0) return '';
  const s = Math.round(ms / 1000);
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;
}

export function useHarvest({ webRef, store, supplierCode, supplierName, orderAt }) {
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState('');
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [avgMs, setAvgMs] = useState(() => avgOf(readTimings()));
  const [lastMs, setLastMs] = useState(0);
  const autoTried = useRef('');

  const readCatalog = useCallback(async () => {
    const web = webRef.current;
    if (!web?.ready()) { const e = new Error('site-not-open'); e.soft = 'Open the supplier’s site first.'; throw e; }
    const out = await web.exec(siteScript(roEnumerate, undefined, supplierName || '')).catch(() => null);
    if (!out) throw new Error('read-failed');
    if (!out.ok) {
      const e = new Error(out.reason || 'read-failed');
      e.soft = out.reason === 'login' ? 'Sign in to the supplier’s site first.'
        : out.reason === 'pick-distributor' ? 'Open New Order for this distributor on the site, then try again.'
          : 'Could not read the supplier’s product list.';
      e.stop = out.reason === 'login' || out.reason === 'pick-distributor';
      throw e;
    }
    if (!out.rows?.length) throw new Error('empty');
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
          if (e.stop) { setError(e.soft || 'Could not read the catalog.'); return false; }
          if (attempt >= HARVEST_RETRIES) {
            setError((e.soft || 'Could not read the full catalog') + ' — kept the existing stock.');
            return false;
          }
          await sleep(1500 * attempt);
        }
      }
      if (!silent) setProgress(`Saving ${rows.length} products to stock…`);
      const r = await legacyHarvestSupplierStock(store, supplierCode, rows, true);
      const took = Date.now() - startedAt;
      setLastMs(took);
      setAvgMs(avgOf(pushTiming(took)));
      setResult(r);
      setProgress(`Saved ${r.stored} products in ${fmtDur(took)}. Live Stock now shows this supplier’s stock.`);
      return true;
    } catch (e) {
      setError((e.message || 'Harvest failed') + ' — kept the existing stock.');
      return false;
    } finally {
      setBusy(false);
    }
  }, [store, supplierCode, busy, readCatalog]);

  useEffect(() => {
    if (!store || !supplierCode || !orderAt) return;
    const key = `${store}|${supplierCode}`;
    if (autoTried.current === key) return;
    let cancelled = false;
    (async () => {
      try {
        const st = await legacySupplierHarvestStatus(store, supplierCode);
        if (cancelled) return;
        const fresh = st?.harvested_at && new Date(st.harvested_at) >= new Date(orderAt);
        autoTried.current = key;
        if (!fresh) {
          await sleep(2500);
          if (!cancelled) harvest({ silent: true });
        }
      } catch { autoTried.current = key; }
    })();
    return () => { cancelled = true; };
  }, [store, supplierCode, orderAt, harvest]);

  return { busy, progress, result, error, harvest, setError, avgMs, lastMs };
}

export function useMatchReview({ store, supplierCode }) {
  const [busy, setBusy] = useState(false);
  const [review, setReview] = useState(null);
  const [error, setError] = useState('');
  const loadedFor = useRef('');

  const load = useCallback(async () => {
    if (!store || !supplierCode) return;
    setError(''); setBusy(true);
    try {
      const r = await legacySupplierMatchReview(store, supplierCode);
      setReview(r); loadedFor.current = `${store}|${supplierCode}`;
    } catch (e) { setError(e.message || 'Could not load the match review.'); }
    finally { setBusy(false); }
  }, [store, supplierCode]);

  const confirm = useCallback(async (item, productCode) => {
    try {
      await legacyConfirmSupplierMatch(store, supplierCode, {
        supplier_product_code: item.supplier_code, supplier_product_name: item.supplier_name,
        product_code: productCode || '',
      });
      await load();
    } catch (e) { setError(e.message || 'Could not save that mapping.'); }
  }, [store, supplierCode, load]);

  return { busy, review, error, load, confirm, setError };
}

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
