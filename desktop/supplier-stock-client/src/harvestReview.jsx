import { useCallback, useRef, useState } from 'react';
import { api } from './api/client.js';
import { harvestRow, roEnumerate, siteScript } from './siteCheck.js';

// Three separate concerns, kept apart (owner 2026-11-05):
//  * useHarvest  -- read the supplier's whole catalog from its open portal and
//    write it to SupplierStock. Nothing else. Live Stock mode then shows it.
//  * useMatchReview + MatchReview -- the "Map supplier products" panel: match the
//    harvested stock to the store's products and save confirmed maps to
//    SupplierProductMatch (so unmapped products become visible in Live Stock).
// Adding to the site's cart is the existing Website site-check flow, not here.

// --- Harvest: read site -> SupplierStock -------------------------------------
export function useHarvest({ webRef, store, supplierCode, session }) {
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState('');
  const [result, setResult] = useState(null);   // { stored } | null
  const [error, setError] = useState('');

  const harvest = useCallback(async () => {
    if (!store || !supplierCode) return;
    setError(''); setResult(null); setBusy(true);
    try {
      const web = webRef.current;
      if (!web?.ready()) { setError('Open the supplier’s site first.'); return; }
      setProgress('Reading the supplier’s product list…');
      const out = await web.exec(siteScript(roEnumerate)).catch(() => null);
      if (!out?.ok) {
        setError(out?.reason === 'login' ? 'Sign in to the supplier’s site first.'
          : out?.reason === 'pick-distributor' ? 'Open New Order for this distributor on the site, then try again.'
          : 'Could not read the supplier’s product list.');
        return;
      }
      const rows = out.rows.map(harvestRow);
      setProgress(`Saving ${rows.length} products to stock…`);
      const r = await api.legacyHarvestSupplierStock(store, supplierCode, rows, session);
      setResult(r);
      setProgress(`Saved ${r.stored} products. Switch to Live Stock to load them into the order.`);
    } catch (e) {
      setError(e.message || 'Harvest failed.');
    } finally {
      setBusy(false);
    }
  }, [webRef, store, supplierCode, session]);

  return { busy, progress, result, error, harvest, setError };
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
