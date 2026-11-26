import React, { useEffect, useRef, useState } from 'react';
import { useAuth } from '../../contexts/AuthContext.jsx';
import {
  billItems,
  crossStoreMatch,
  productCoreBulk,
  purchaseBill,
  searchProducts,
} from '../../services/stockEnquiryService.js';
import { BillDetailsModal } from '../../components/BillDetailsModal.jsx';
import { Icon } from '../../ui/icons.jsx';
import { formatCurrency, formatDate } from '../../utilities/format.js';
import { isSuperAdmin } from '../../navigation/access.js';
import './stockMatrix.css';

const EMPTY_RESULT = { stores: [] };

function money(v) {
  return v == null ? '—' : formatCurrency(v);
}
function date(v) {
  return v == null ? '—' : formatDate(v);
}

/** Closes a modal on Escape — shared by every drawer in this view. */
function useEscapeToClose(onClose) {
  useEffect(() => {
    const handler = (e) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);
}

function GrnDrawer({ tenantId, storeId, state, onClose }) {
  const [items, setItems] = useState(null);
  const [loading, setLoading] = useState(true);
  useEscapeToClose(onClose);

  useEffect(() => {
    let live = true;
    setLoading(true);
    purchaseBill(tenantId, storeId, state.grnNo)
      .then((rows) => { if (live) setItems(rows); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [tenantId, storeId, state.grnNo]);

  const total = (items ?? []).reduce((sum, r) => sum + (r.qty ?? 0) * (r.ptr ?? 0), 0);

  return (
    <div className="ntm-sm-modal-overlay" onClick={onClose}>
      <div className="ntm-sm-modal" onClick={(e) => e.stopPropagation()}>
        <div className="ntm-sm-modal__head">
          <strong>{state.storeLabel} — GRN {state.grnNo}{state.supplier ? ` · ${state.supplier}` : ''}</strong>
          <button type="button" className="ntm-sm-close-btn" onClick={onClose}>✕ Close</button>
        </div>
        <div className="ntm-sm-modal__body">
          {loading ? (
            <div className="ntm-sm-empty">Loading…</div>
          ) : items && items.length > 0 ? (
            <>
              <table>
                <thead>
                  <tr><th>Product</th><th>Batch</th><th>Expiry</th><th className="ntm-sm-num">Qty</th><th className="ntm-sm-num">Free</th><th className="ntm-sm-num">PTR</th><th className="ntm-sm-num">MRP</th></tr>
                </thead>
                <tbody>
                  {items.map((r, i) => (
                    <tr key={i}>
                      <td>{r.product_name ?? '—'}</td>
                      <td>{r.batch ?? '—'}</td>
                      <td>{date(r.expiry)}</td>
                      <td className="ntm-sm-num">{r.qty ?? 0}</td>
                      <td className="ntm-sm-num">{r.free ?? 0}</td>
                      <td className="ntm-sm-num">{money(r.ptr)}</td>
                      <td className="ntm-sm-num">{money(r.mrp)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="ntm-sm-modal__total">GRN value: <strong>{money(total)}</strong></div>
            </>
          ) : (
            <div className="ntm-sm-empty">No line items found for this GRN.</div>
          )}
        </div>
      </div>
    </div>
  );
}

// Fetches EVERY active target's core data in a single bulk request, keyed by
// store id — avoids the N-concurrent-requests contention that left most
// store columns stuck on "Loading..." (see productCoreBulk in
// stockEnquiryService.js).
function useAllStoresCore(tenantId, targets) {
  const [coreByStore, setCoreByStore] = useState(new Map());
  const [loading, setLoading] = useState(targets.length > 0);
  const key = targets.map((t) => `${t.storeId}:${t.productCode}`).join('|');

  useEffect(() => {
    if (targets.length === 0) {
      setCoreByStore(new Map());
      setLoading(false);
      return undefined;
    }
    let live = true;
    setLoading(true);
    productCoreBulk(
      tenantId,
      targets.map((t) => ({ store_id: t.storeId, product_code: t.productCode })),
      { months: 4 },
    )
      .then(({ items }) => {
        if (!live) return;
        setCoreByStore(new Map((items || []).map((item) => [item.store_id, item])));
      })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId, key]);

  return { coreByStore, loading };
}

function StoreCoreCells({ target, core, loading, restricted, column, onOpenBill, onOpenGrn }) {
  if (restricted) {
    return (
      <>
        <div className="ntm-sm-cell ntm-sm-cell--purchase" style={{ gridRow: 3, gridColumn: column }}>
          <div className="ntm-sm-empty">Warehouse purchase detail — super admin only</div>
        </div>
        <div className="ntm-sm-cell ntm-sm-cell--sales" style={{ gridRow: 4, gridColumn: column }}>
          <div className="ntm-sm-empty">Warehouse sales detail — super admin only</div>
        </div>
      </>
    );
  }

  return (
    <>
      <div className="ntm-sm-cell ntm-sm-cell--purchase" style={{ gridRow: 3, gridColumn: column }}>
        {loading ? (
          <div className="ntm-sm-empty">Loading…</div>
        ) : core?.purchases?.length ? (
          <table className="ntm-sm-purchase-grid">
            <colgroup>
              <col className="ntm-sm-pcol--date" />
              <col className="ntm-sm-pcol--qty" />
              <col className="ntm-sm-pcol--free" />
              <col className="ntm-sm-pcol--ptr" />
              <col className="ntm-sm-pcol--mrp" />
              <col className="ntm-sm-pcol--cost" />
              <col className="ntm-sm-pcol--supplier" />
            </colgroup>
            <thead>
              <tr>
                <th className="ntm-sm-pcol--date">Date</th>
                <th className="ntm-sm-num ntm-sm-pcol--qty">Qty</th>
                <th className="ntm-sm-num ntm-sm-pcol--free">Free</th>
                <th className="ntm-sm-num ntm-sm-pcol--ptr">PTR</th>
                <th className="ntm-sm-num ntm-sm-pcol--mrp">MRP</th>
                <th className="ntm-sm-num ntm-sm-pcol--cost">Cost</th>
                <th className="ntm-sm-pcol--supplier">Supplier</th>
              </tr>
            </thead>
            <tbody>
              {core.purchases.slice(0, 40).map((p, i) => (
                <tr key={i} className="ntm-sm-row-clickable" onClick={(e) => { e.stopPropagation(); if (p.grn_no) onOpenGrn(target, p); }}>
                  <td className="ntm-sm-pcol--date">{date(p.date)}</td>
                  <td className="ntm-sm-num ntm-sm-pcol--qty">{p.qty ?? 0}</td>
                  <td className="ntm-sm-num ntm-sm-pcol--free">{p.free ?? 0}</td>
                  <td className="ntm-sm-num ntm-sm-pcol--ptr">{money(p.ptr)}</td>
                  <td className="ntm-sm-num ntm-sm-pcol--mrp">{money(p.mrp)}</td>
                  <td className="ntm-sm-num ntm-sm-pcol--cost">{money(p.cost)}</td>
                  <td className="ntm-sm-pcol--supplier">{p.supplier || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <div className="ntm-sm-empty">No purchase history.</div>}
      </div>

      <div className="ntm-sm-cell ntm-sm-cell--sales" style={{ gridRow: 4, gridColumn: column }}>
        {loading ? (
          <div className="ntm-sm-empty">Loading…</div>
        ) : core?.sales?.length ? (
          <table>
            <thead>
              <tr><th>Date</th><th>Customer</th><th className="ntm-sm-num">Qty</th></tr>
            </thead>
            <tbody>
              {core.sales.slice(0, 40).map((s, i) => (
                <tr key={i} className="ntm-sm-row-clickable" onClick={(e) => { e.stopPropagation(); if (s.bill_no) onOpenBill(target, s); }}>
                  <td>{date(s.date)}</td>
                  <td>{s.customer ?? '—'}</td>
                  <td className="ntm-sm-num">{s.qty ?? 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <div className="ntm-sm-empty">No sales history.</div>}
      </div>
    </>
  );
}

/**
 * Store-column row-band stock matrix: 3 always-visible bands per store
 * column (Store Grid / Purchase / Sales) — Chart and Batch are intentionally
 * omitted (owner: "quick check only 3 panels, remove batches"). No
 * Sales-or-Purchase toggle (that toggle only exists in the Quick Stock
 * *compact* variant, where its two rotated buttons can visually overlap in a
 * short row; this full layout sidesteps that bug by giving Purchase and
 * Sales their own rows). Click a sale/GRN row for its full bill. Built on this app's own
 * authenticated stock_availability endpoints — no changes made to Quick
 * Stock or supplier-stock-client.
 *
 * NMW (warehouse) access: every user sees NMW's column in the Store Grid
 * (stock + MRP), matching what the supplier stock client already shows a
 * non-admin. Only Purchase/Sales detail for NMW is super-admin-only -- a
 * non-admin selecting a product still gets full Purchase/Sales for every
 * OTHER store, just not NMW's, rather than losing the whole screen.
 */
export function StockMatrixView({ title = 'Stock Vertical' }) {
  const { user, tenantId, stores } = useAuth();
  const superAdmin = isSuperAdmin(user);

  const isNmw = (storeCode) => String(storeCode || '').toUpperCase() === 'NMW';

  const visibleStores = (stores || []).filter((s) => String(s.tenant_id) === String(tenantId));

  const [query, setQuery] = useState('');
  const [onlyStock, setOnlyStock] = useState(false);
  const [result, setResult] = useState(EMPTY_RESULT);
  const [status, setStatus] = useState('idle');
  const [activeProductName, setActiveProductName] = useState(null);
  const [activeTargets, setActiveTargets] = useState([]);
  const [billDrawer, setBillDrawer] = useState(null);
  const [grnDrawer, setGrnDrawer] = useState(null);
  // NMW's Purchase/Sales detail is super-admin-only -- never fetched (not just
  // hidden) for anyone else, so a non-admin never pulls NMW's transaction data.
  const coreTargets = superAdmin ? activeTargets : activeTargets.filter((t) => !isNmw(t.storeLabel));
  const { coreByStore, loading: coreLoading } = useAllStoresCore(tenantId, coreTargets);
  const [debQuery, setDebQuery] = useState('');
  const debounceRef = useRef(null);
  const ticketRef = useRef(0);
  const selectTicketRef = useRef(0);
  const autoSelectTimerRef = useRef(null);

  useEffect(() => {
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => setDebQuery(query), 250);
    return () => clearTimeout(debounceRef.current);
  }, [query]);

  useEffect(() => {
    setActiveProductName(null);
    setActiveTargets([]);
  }, [debQuery, tenantId]);

  useEffect(() => {
    if (!tenantId) return undefined;
    if (!debQuery.trim()) {
      setResult(EMPTY_RESULT);
      setStatus('idle');
      return undefined;
    }
    const ticket = ++ticketRef.current;
    setStatus('loading');
    searchProducts(tenantId, debQuery.trim(), { onlyStock })
      .then((data) => {
        if (ticket !== ticketRef.current) return;
        setResult(data);
        setStatus('success');
        const firstHit = (data.stores || [])
          .flatMap((s) => (s.products || []).map((p) => ({ storeId: s.store_id, product: p })))
          .find((row) => row.product.product_code);
        if (autoSelectTimerRef.current) clearTimeout(autoSelectTimerRef.current);
        if (firstHit) {
          autoSelectTimerRef.current = setTimeout(() => {
            if (ticket !== ticketRef.current) return;
            selectProduct(firstHit.storeId, firstHit.product);
          }, 450);
        }
      })
      .catch(() => {
        if (ticket !== ticketRef.current) return;
        setResult(EMPTY_RESULT);
        setStatus('error');
      });
    return () => {
      if (autoSelectTimerRef.current) clearTimeout(autoSelectTimerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId, debQuery, onlyStock]);

  const totalProducts = result.stores.reduce((sum, s) => sum + (s.products?.length || 0), 0);
  const productsByStore = new Map(result.stores.map((s) => [s.store_id, s.products || []]));
  const frames = visibleStores.map((s) => ({
    store_id: s.store_id,
    label: s.store_code ?? s.store_name ?? 'Store',
    name: s.store_name ?? null,
    products: productsByStore.get(s.store_id) ?? [],
  }));

  function ownMatchInStore(storeId, productName) {
    return productsByStore.get(storeId)?.find((p) => p.product_name === productName);
  }

  function selectProduct(sourceStoreId, product) {
    if (!product.product_code || !product.product_name) return;
    const selectTicket = ++selectTicketRef.current;
    setActiveProductName(product.product_name);
    const exact = frames
      .map((f) => {
        const own = ownMatchInStore(f.store_id, product.product_name);
        return own?.product_code ? { storeId: f.store_id, storeLabel: f.label, storeName: f.name, productCode: own.product_code } : null;
      })
      .filter(Boolean);
    setActiveTargets(exact);

    const matchedIds = new Set(exact.map((t) => t.storeId));
    const unresolvedIds = frames.map((f) => f.store_id).filter((id) => id !== sourceStoreId && !matchedIds.has(id));
    if (!unresolvedIds.length) return;
    crossStoreMatch(tenantId, sourceStoreId, product.product_code, product.product_name, unresolvedIds)
      .then(({ results }) => {
        if (selectTicket !== selectTicketRef.current) return;
        const extra = (results || [])
          .filter((r) => r.product?.product_code)
          .map((r) => {
            const label = frames.find((f) => f.store_id === r.store_id)?.label ?? r.store_id;
            const name = frames.find((f) => f.store_id === r.store_id)?.name ?? null;
            return { storeId: r.store_id, storeLabel: label, storeName: name, productCode: r.product.product_code };
          });
        if (extra.length) setActiveTargets((cur) => [...cur, ...extra]);
      })
      .catch(() => { /* leave unresolved stores as "Not stocked here" */ });
  }

  const columnOf = (storeId) => {
    const idx = frames.findIndex((f) => f.store_id === storeId);
    return idx >= 0 ? idx + 2 : 1;
  };

  return (
    <div className="ntm-sm">
      <div className="ntm-sm-head">
        <span className="ntm-sm-head__title"><Icon name="search" size={16} /> {title}</span>
        <div className="ntm-sm-search">
          <Icon name="search" size={14} />
          <input autoFocus value={query} placeholder="Search product name…" onChange={(e) => setQuery(e.target.value)} />
        </div>
        <label className="ntm-sm-check">
          <input type="checkbox" checked={onlyStock} onChange={(e) => setOnlyStock(e.target.checked)} /> In-stock only
        </label>
        <span className="ntm-sm-status">
          {status === 'loading' ? 'Searching…' : query.trim() ? `${totalProducts} matches` : ''}
        </span>
        {!superAdmin && (
          <span className="ntm-sm-status ntm-sm-status--muted">Warehouse (NMW) purchase/sales detail — super admin only</span>
        )}
      </div>

      <div className="ntm-sm-body">
        {status === 'error' && <div className="ntm-sm-empty-page">Search failed. Try again.</div>}

        {activeProductName && (
          <div className="ntm-sm-active-product">
            <span>Showing: <strong>{activeProductName}</strong></span>
            <button type="button" className="ntm-sm-close-btn" onClick={() => { setActiveProductName(null); setActiveTargets([]); }}>✕ Clear</button>
          </div>
        )}

        <div
          className="ntm-sm-grid"
          style={{
            gridTemplateColumns: `var(--ntm-sm-label-w, 32px) repeat(${frames.length}, minmax(240px, 1fr))`,
            gridTemplateRows: 'auto minmax(120px, 0.9fr) minmax(90px, 0.75fr) minmax(100px, 0.85fr)',
          }}
        >
          <div className="ntm-sm-corner" style={{ gridRow: 1, gridColumn: 1 }} />
          {frames.map((f, i) => (
            <div className="ntm-sm-colhead" key={f.store_id} style={{ gridRow: 1, gridColumn: i + 2 }}>
              <span className="ntm-sm-colhead__code">{f.label}</span>
              {f.name && f.name !== f.label && <span className="ntm-sm-colhead__name" title={f.name}>{f.name}</span>}
            </div>
          ))}

          <div className="ntm-sm-rowlabel ntm-sm-rowlabel--grid" style={{ gridRow: 2, gridColumn: 1 }}><span>Store Grid</span></div>
          {frames.map((branch, i) => (
            <div className="ntm-sm-cell ntm-sm-cell--grid" key={branch.store_id} style={{ gridRow: 2, gridColumn: i + 2 }}>
              <div className="ntm-sm-row ntm-sm-row--head">
                <span>Product</span><span>Unit</span><span className="ntm-sm-num">Stock</span>
              </div>
              {branch.products.length === 0 ? (
                <div className="ntm-sm-placeholder">
                  {status === 'loading' ? 'Searching…' : query.trim() ? 'No matching product' : 'Type to search'}
                </div>
              ) : (
                branch.products.map((p, pi) => {
                  const isActive = activeTargets.some((t) => t.storeId === branch.store_id && t.productCode === p.product_code);
                  return (
                    <button
                      key={`${p.product_code}-${pi}`}
                      type="button"
                      title="Click to show detail across every band"
                      className={`ntm-sm-row${isActive ? ' is-active' : ''}`}
                      onClick={() => selectProduct(branch.store_id, p)}
                    >
                      <span>
                        <span className={`ntm-sm-dot ${(p.stock ?? 0) > 0 ? 'ntm-sm-dot--in' : 'ntm-sm-dot--out'}`} aria-hidden="true" />
                        {p.product_name ?? '—'}
                      </span>
                      <span className="ntm-sm-dim">{p.sale_unit ?? '—'}</span>
                      <span className="ntm-sm-num">{(p.stock ?? 0).toLocaleString('en-IN')}</span>
                    </button>
                  );
                })
              )}
            </div>
          ))}

          <div className="ntm-sm-rowlabel ntm-sm-rowlabel--purchase" style={{ gridRow: 3, gridColumn: 1 }}><span>Purchase</span></div>
          <div className="ntm-sm-rowlabel ntm-sm-rowlabel--sales" style={{ gridRow: 4, gridColumn: 1 }}><span>Sales</span></div>

          {activeProductName && activeTargets.length > 0 ? (
            activeTargets.map((t) => (
              <StoreCoreCells
                key={t.storeId}
                target={t}
                core={coreByStore.get(t.storeId) ?? null}
                loading={coreLoading}
                restricted={!superAdmin && isNmw(t.storeLabel)}
                column={columnOf(t.storeId)}
                onOpenBill={(store, sale) => setBillDrawer({ store, state: { storeLabel: store.storeLabel, storeName: store.storeName, billNo: sale.bill_no ?? '', billDate: sale.date ?? null, customer: sale.customer } })}
                onOpenGrn={(store, purchase) => setGrnDrawer({ store, state: { storeLabel: store.storeLabel, grnNo: purchase.grn_no ?? '', supplier: purchase.supplier ?? null } })}
              />
            ))
          ) : (
            frames.map((f, i) =>
              [3, 4].map((row) => (
                <div key={`${f.store_id}-${row}`} className="ntm-sm-cell" style={{ gridRow: row, gridColumn: i + 2 }}>
                  <div className="ntm-sm-empty">Select a product above.</div>
                </div>
              )),
            )
          )}
        </div>
      </div>

      {billDrawer && (
        <BillDetailsModal
          storeLabel={billDrawer.state.storeLabel}
          storeName={billDrawer.state.storeName}
          billNo={billDrawer.state.billNo}
          billDate={billDrawer.state.billDate}
          customer={billDrawer.state.customer}
          fetchItems={() => billItems(tenantId, billDrawer.store.storeId, billDrawer.state.billNo, billDrawer.state.billDate)}
          onClose={() => setBillDrawer(null)}
        />
      )}
      {grnDrawer && (
        <GrnDrawer tenantId={tenantId} storeId={grnDrawer.store.storeId} state={grnDrawer.state} onClose={() => setGrnDrawer(null)} />
      )}
    </div>
  );
}
