import { useEffect, useRef, useState } from 'react';
import { api } from './api/client.js';
import { pwIsWarehouseCard } from './procurementWorkspaceView.js';

// Supplier Recommendation column -- one per selected product, for ANY product
// (keyed by store + product code, not a procurement line): ranked supplier
// cards tagged Best / Frequent / Latest / Live / Warehouse (backend
// suggestion_service -- the Purchase Manager's own recommendation blend), in
// the web Purchase Manager's card layout (Cost / PTR / Margin / MRP, last
// purchase, frequency, Assign), then the other stores' stock of the same
// product, non-moving first (stock that can be moved here instead of buying).
// Keyboard: the grid's Right Arrow focuses the panel; Up/Down pick a supplier,
// Enter assigns, Left/Esc go back to the quantity.

const TAG_LABEL = { best: 'Best', frequent: 'Frequent', latest: 'Latest', live: 'Live', warehouse: 'Warehouse' };
const TAG_TITLE = {
  best: 'Top recommendation — recent purchase, frequency, price and live stock combined',
  frequent: 'Bought from most often',
  latest: 'Most recent purchase',
  live: 'Has this product in its live stock list',
  warehouse: 'Our warehouse stock (stock transfer)',
};

// In-memory cache for the session (a product re-selected is instant); a short
// settle delay so holding Down does not fire one request per row passed.
const cache = new Map();
const CACHE_MS = 3 * 60 * 1000;

export function useProductSuggestions({ tenantId, storeId, productCode, session }) {
  const [state, setState] = useState({ loading: false, error: '', data: null });
  const key = tenantId && storeId && productCode != null ? `${tenantId}|${storeId}|${productCode}` : '';
  useEffect(() => {
    if (!key) { setState({ loading: false, error: '', data: null }); return undefined; }
    const hit = cache.get(key);
    if (hit && Date.now() - hit.at < CACHE_MS) { setState({ loading: false, error: '', data: hit.data }); return undefined; }
    let cancelled = false;
    setState({ loading: true, error: '', data: null });
    const t = setTimeout(() => {
      api.procurementProductSuggestions(tenantId, storeId, productCode, session)
        .then((data) => { cache.set(key, { at: Date.now(), data }); if (!cancelled) setState({ loading: false, error: '', data }); })
        .catch((e) => { if (!cancelled) setState({ loading: false, error: e.message || 'Could not load suggestions.', data: null }); });
    }, 120);
    return () => { cancelled = true; clearTimeout(t); };
  }, [key, tenantId, storeId, productCode, session]);
  return { ...state, suppliers: state.data?.suppliers || [], otherStores: state.data?.other_stores || [] };
}

export function invalidateProductSuggestions() { cache.clear(); }

function qty(v) {
  const n = Number(v);
  return v == null || v === '' || !Number.isFinite(n) ? '—' : n.toLocaleString(undefined, { maximumFractionDigits: 2 });
}
function money(v) {
  const n = Number(v);
  return v == null || v === '' || !Number.isFinite(n) ? '—' : `₹${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}
function dmy(v) {
  const p = String(v || '').slice(0, 10).split('-');
  return p.length === 3 ? `${p[2]}/${p[1]}/${p[0].slice(2)}` : '—';
}

// Margin % = (PTR - Cost) / Cost -- markup on cost, the web Purchase
// Manager's costMarginPercent (its Margin Report definition); falls back to
// (MRP - PTR) / MRP only when no cost was recorded.
function marginOf(ptr, cost, mrp) {
  const p = Number(ptr); const c = Number(cost); const m = Number(mrp);
  if (ptr == null || !Number.isFinite(p)) return null;
  if (cost != null && c > 0) return ((p - c) / c) * 100;
  if (mrp != null && m > 0) return ((m - p) / m) * 100;
  return null;
}

export function SuggestionPanel({
  suggestions, active, cursor, onCursor, onAssign, onExit, assignQty, assignedSupplier, canAssign, busy, panelRef,
  productMrp = null, hasProduct = true,
}) {
  const { loading, error, suppliers, otherStores } = suggestions;
  const rowRefs = useRef([]);
  useEffect(() => { if (active) rowRefs.current[cursor]?.scrollIntoView({ block: 'nearest' }); }, [active, cursor]);
  const nonMoving = otherStores.filter((s) => s.non_moving);
  const moving = otherStores.filter((s) => !s.non_moving && Number(s.stock) > 0);

  const onKeyDown = (e) => {
    if (!suppliers.length && (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'Enter')) {
      e.preventDefault();
      return;
    }
    if (e.key === 'ArrowDown') { e.preventDefault(); onCursor(Math.min(cursor + 1, suppliers.length - 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); onCursor(Math.max(cursor - 1, 0)); }
    else if (e.key === 'Enter') { e.preventDefault(); if (suppliers[cursor]) onAssign(suppliers[cursor]); }
    else if (e.key === 'ArrowLeft' || e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); onExit(); }
  };

  return (
    <section className={`sg-panel${active ? ' sg-panel--active' : ''}`} ref={panelRef} tabIndex={-1} onKeyDown={onKeyDown}
      aria-label="Supplier recommendation">
      <div className="sg-head">
        <span className="sg-title">Supplier Recommendation</span>
        <span className="sg-sub">{active ? '↑↓ pick · Enter assign · ← back' : 'Ranked by recent purchase, frequency & price · → to pick'}</span>
      </div>
      <div className="sg-body">
        {!hasProduct && <div className="sg-none">Select a product.</div>}
        {hasProduct && loading && <div className="sg-none">Loading supplier recommendations…</div>}
        {hasProduct && error && <div className="sg-none">{error}</div>}
        {hasProduct && !loading && !error && (
          <>
            <div className="sg-list" role="listbox" aria-label="Suppliers">
              {suppliers.map((s, i) => {
                const sel = active && i === cursor;
                const isAssigned = Boolean(assignedSupplier) && assignedSupplier === s.supplier_code;
                const ownedElsewhere = Boolean(assignedSupplier) && !isAssigned;
                const warehouse = pwIsWarehouseCard(s);
                const mrp = s.last_mrp ?? s.live_mrp ?? productMrp ?? null;
                const margin = marginOf(s.ptr, s.last_item_cost, mrp);
                const discount = s.last_discount != null && s.last_discount !== '' ? s.last_discount : s.live_discount;
                const disabled = warehouse || !canAssign || ownedElsewhere || busy;
                return (
                  <div key={s.supplier_code} ref={(el) => { rowRefs.current[i] = el; }}
                    role="option" aria-selected={sel}
                    className={`sg-card${sel ? ' sg-card--sel' : ''}${isAssigned ? ' sg-card--assigned' : ''}${s.tags?.includes('best') ? ' sg-card--best' : ''}`}
                    onClick={() => onCursor(i)}
                    onDoubleClick={() => { if (!disabled) onAssign(s); }}
                    title={`${s.supplier_name || s.supplier_code} (${s.supplier_code})`}>
                    {(s.tags?.length > 0 || isAssigned) && (
                      <div className="sg-tags">
                        {(s.tags || []).map((t) => <span key={t} className={`sg-tag sg-tag--${t}`} title={TAG_TITLE[t]}>{TAG_LABEL[t] || t}</span>)}
                        {isAssigned && <span className="sg-tag sg-tag--assigned">Assigned</span>}
                      </div>
                    )}
                    <div className="sg-card-name">{s.supplier_name || s.supplier_code}</div>
                    <div className="sg-stats">
                      <span className="sg-stat"><b>{money(s.last_item_cost)}</b><label>Cost</label></span>
                      <span className="sg-stat"><b>{money(s.ptr)}</b><label>PTR</label></span>
                      <span className="sg-stat"><b className={margin != null ? 'sg-margin' : undefined}>{margin != null ? `${margin.toFixed(2)}%` : '—'}</b><label>Margin</label></span>
                      <span className="sg-stat"><b>{money(mrp)}</b><label>MRP</label></span>
                    </div>
                    <div className="sg-facts">
                      <span>Last Purchase: {s.last_grn_date ? dmy(s.last_grn_date) : 'No history'}</span>
                      {Number(s.live_stock) > 0 && <span className="sg-live">Stock {qty(s.live_stock)}{s.live_scheme ? ` · ${s.live_scheme}` : ''}</span>}
                      {discount != null && discount !== '' && <span>Disc {qty(discount)}%</span>}
                      <span>Freq {qty(s.purchase_frequency ?? 0)}</span>
                    </div>
                    <button type="button" className="sg-assign" disabled={disabled}
                      title={warehouse ? 'Warehouse stock (ST_*) cannot be assigned as a supplier'
                        : isAssigned ? 'Already assigned to this supplier'
                        : ownedElsewhere ? 'Already assigned to another supplier — remove it in Info › Suppliers to reassign'
                          : canAssign ? 'Assign the remaining quantity to this supplier (Enter)' : 'Nothing left to assign — set an order qty first'}
                      onClick={(e) => { e.stopPropagation(); if (!disabled) onAssign(s); }}>
                      {warehouse ? 'Warehouse stock' : isAssigned ? 'Assigned' : busy && sel ? 'Assigning…' : `Assign ${Number(assignQty) > 0 ? qty(assignQty) : ''}`.trim()}
                    </button>
                  </div>
                );
              })}
              {!suppliers.length && <div className="sg-none">No purchase history or live stock for this product.</div>}
            </div>

            <div className="sg-stores">
              <div className="sg-stores-title">
                Other stores — non-moving stock
                {nonMoving.length > 0 && <b className="sg-nm-total">{qty(nonMoving.reduce((t, s) => t + Number(s.stock || 0), 0))} available</b>}
              </div>
              {nonMoving.length > 0 ? (
                <table className="ow-intel-table sg-stores-table">
                  <colgroup><col style={{ width: '22%' }} /><col style={{ width: '20%' }} /><col style={{ width: '22%' }} /><col style={{ width: '36%' }} /></colgroup>
                  <thead><tr><th>Store</th><th className="ow-num">Stock</th><th className="ow-num">No sale</th><th>Last purchase</th></tr></thead>
                  <tbody>
                    {nonMoving.map((s) => (
                      <tr key={s.store_id} title={`${s.store_name || ''} · ${s.product_name || ''} (#${s.product_code})`}>
                        <td><b>{s.store_code}</b></td>
                        <td className="ow-num"><b>{qty(s.stock)}</b></td>
                        <td className="ow-num">{s.days_since_sale == null ? 'never' : `${s.days_since_sale}d`}</td>
                        <td>{dmy(s.last_purchase_date)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : <div className="sg-none">No other store holds this product without selling it.</div>}
              {moving.length > 0 && (
                <div className="sg-moving" title="Stores that hold this product and are still selling it">
                  Selling elsewhere: {moving.map((s) => `${s.store_code} ${qty(s.stock)}`).join(' · ')}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </section>
  );
}
