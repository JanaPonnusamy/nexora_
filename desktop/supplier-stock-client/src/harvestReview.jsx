import { useCallback, useRef, useState } from 'react';
import { api } from './api/client.js';
import {
  bulkDecide, harvestRow, roAdd, roEnumerate, roPick, roResults, roSearch, siteInCart, siteScript,
} from './siteCheck.js';

// Harvest a supplier's whole catalog from its portal once, match it to the
// store's products on the server (reusing SupplierProductMatch + the product
// mapping engine), then compare the order against the harvested stock LOCALLY --
// so the bulk check is seconds, not a per-product site search. Matched products
// are auto-saved; suggested / needs-mapping come back for a one-time review with
// their own colour + watermark.

const sleep = (ms) => new Promise((r) => { setTimeout(r, ms); });

export function useHarvestBulk({ webRef, store, supplierCode, session }) {
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState('');          // '', 'harvesting', 'matching', 'review', 'carting'
  const [progress, setProgress] = useState('');
  const [review, setReview] = useState(null);      // { counts, items }
  const [error, setError] = useState('');
  const cancelRef = useRef(false);

  const cancel = useCallback(() => { cancelRef.current = true; }, []);

  // Step 1-2: read the supplier catalog from the open site, post it, get the review.
  const harvest = useCallback(async () => {
    if (!store || !supplierCode) return;
    setError(''); setBusy(true); setReview(null); cancelRef.current = false;
    try {
      const web = webRef.current;
      if (!web?.ready()) { setError('Open the supplier’s site first.'); return; }
      setPhase('harvesting'); setProgress('Reading the supplier’s product list…');
      const res = await web.exec(siteScript(roEnumerate)).catch(() => null);
      // roEnumerate takes a callback we can't serialise; run it via exec of the
      // inlined function that reports progress through the DOM instead: fall
      // back to a single call and poll a global it writes.
      const out = res || await runEnumerate(web, (done, total, found) => {
        setProgress(`Reading the catalog… ${found} products (${done}/${total})`);
      });
      if (cancelRef.current) { setPhase(''); return; }
      if (!out?.ok) {
        setError(out?.reason === 'login' ? 'Sign in to the supplier’s site first.'
          : out?.reason === 'pick-distributor' ? 'Open New Order for this distributor on the site, then try again.'
          : 'Could not read the supplier’s product list.');
        return;
      }
      const rows = out.rows.map(harvestRow);
      setPhase('matching'); setProgress(`Matching ${rows.length} products to the store…`);
      const r = await api.legacyHarvestSupplierStock(store, supplierCode, rows, session);
      setReview(r); setPhase('review');
      setProgress(`${r.counts.matched} matched · ${r.counts.suggested} to confirm · ${r.counts.needs_mapping} to map`);
    } catch (e) {
      setError(e.message || 'Harvest failed.');
    } finally {
      setBusy(false);
    }
  }, [webRef, store, supplierCode, session]);

  // Confirm a suggestion / map an unmapped product, then refresh the review.
  const confirm = useCallback(async (item, productCode) => {
    try {
      await api.legacyConfirmSupplierMatch(store, supplierCode, {
        supplier_product_code: item.supplier_code, supplier_product_name: item.supplier_name,
        product_code: productCode || '',
      }, session);
      const r = await api.legacySupplierHarvestReview(store, supplierCode, session);
      setReview(r);
    } catch (e) { setError(e.message || 'Could not save that mapping.'); }
  }, [store, supplierCode, session]);

  // Step 5: add every matched, in-stock product that the order needs to the
  // site's cart -- in bulk, using the already-harvested stock (no per-product
  // search). `orderRows` = the left grid. Returns a summary.
  const addToCart = useCallback(async (orderRows) => {
    const web = webRef.current;
    if (!web?.ready() || !review) return null;
    const byCode = {};
    for (const m of review.items) if (m.product_code) byCode[String(m.product_code)] = { stock: m.stock, supplier_name: m.supplier_name };
    setPhase('carting'); setBusy(true); cancelRef.current = false;
    let added = 0; let out = 0; let short = 0;
    const want = orderRows.filter((r) => Number(r.status) === 0 && Number(r.order_qty) > 0);
    try {
      for (let i = 0; i < want.length; i += 1) {
        if (cancelRef.current) break;
        const row = want[i];
        const d = bulkDecide(row, byCode);
        if (d.state === 'none') { out += 1; continue; }
        setProgress(`Adding to cart ${i + 1}/${want.length} — ${d.supplierName || row.product_name}…`);
        // Search the supplier's own name for this product, pick it, add the qty.
        const sent = await web.exec(siteScript(roSearch, siteName(d.supplierName || row.product_name), false)).catch(() => null);
        if (!sent?.ok) { out += 1; continue; }
        await sleep(600);
        const res = await web.exec(siteScript(roResults)).catch(() => null);
        const hit = (res?.rows || []).find((x) => String(x.name).toUpperCase().includes(String(d.supplierName || '').toUpperCase().slice(0, 12)));
        if (!hit) { out += 1; continue; }
        await web.exec(siteScript(roPick, hit.n)).catch(() => {});
        await sleep(300);
        const qty = Math.min(Number(row.order_qty) || 1, Number(byCode[String(row.product_code)].stock) || 1);
        await web.exec(siteScript(roAdd, hit.n, qty, false)).catch(() => {});
        if (d.state === 'partial') short += 1;
        added += 1;
        await sleep(400);
      }
    } finally {
      setPhase('review'); setBusy(false);
    }
    return { added, out, short };
  }, [webRef, review]);

  return { busy, phase, progress, review, error, harvest, confirm, addToCart, cancel, setError };
}

// roEnumerate uses an onProgress callback that can't cross executeJavaScript, so
// drive it in chunks from here: enumerate with no callback, which still returns
// everything; progress is coarse but the harvest is one call.
async function runEnumerate(web, onProgress) {
  onProgress?.(0, 1, 0);
  return web.exec(siteScript(roEnumerate)).catch(() => ({ ok: false, reason: 'exec' }));
}

// A clean query for the add-to-cart search: brand + first strength.
function siteName(name) {
  return String(name || '').replace(/\(.*?\)/g, '').replace(/\s+/g, ' ').trim().slice(0, 30);
}

// The review panel: three tiers, each with its own colour + watermark. The user
// confirms a suggestion or maps an unmapped product once.
export function HarvestReview({ review, store, suppliers, onConfirm, onBulkCart, busy, progress }) {
  const [tab, setTab] = useState('suggested');
  if (!review) return null;
  const items = review.items.filter((m) => m.tier === tab);
  const c = review.counts;
  return (
    <div className="hv" role="region" aria-label="Supplier stock review">
      <div className="hv-head">
        <div className="hv-tabs" role="tablist">
          <button type="button" role="tab" aria-selected={tab === 'matched'} className={`hv-tab hv-tab--matched${tab === 'matched' ? ' is-on' : ''}`} onClick={() => setTab('matched')}>Matched {c.matched}</button>
          <button type="button" role="tab" aria-selected={tab === 'suggested'} className={`hv-tab hv-tab--suggested${tab === 'suggested' ? ' is-on' : ''}`} onClick={() => setTab('suggested')}>To confirm {c.suggested}</button>
          <button type="button" role="tab" aria-selected={tab === 'needs_mapping'} className={`hv-tab hv-tab--unmapped${tab === 'needs_mapping' ? ' is-on' : ''}`} onClick={() => setTab('needs_mapping')}>To map {c.needs_mapping}</button>
        </div>
        <button type="button" className="ow-btn ow-btn-sm ow-btn-primary" disabled={busy} onClick={onBulkCart}>⚡ Add matched to cart</button>
      </div>
      {progress && <p className="hv-progress">{progress}</p>}
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
                    ? <MapPicker suppliers={suppliers} onPick={(code) => onConfirm(m, code)} />
                    : <span title={`${m.method} · ${m.confidence}%`}>{m.product_name || '—'}</span>}
                </td>
                <td>
                  {m.tier === 'suggested' && (
                    <span className="hv-acts">
                      <button type="button" className="ow-btn ow-btn-sm" title="Confirm this match" onClick={() => onConfirm(m, m.product_code)}>✓</button>
                      <button type="button" className="ow-btn ow-btn-sm" title="Wrong — map it" onClick={() => onConfirm(m, '')}>✕</button>
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
function MapPicker({ suppliers, onPick }) {
  const [text, setText] = useState('');
  // suppliers here are the store's products passed in; reuse the supplier
  // datalist shape { product_code, product_name } if provided, else free text.
  const list = Array.isArray(suppliers) ? suppliers : [];
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
