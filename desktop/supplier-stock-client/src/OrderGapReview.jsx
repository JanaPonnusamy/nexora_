// Order Gap Review -- a purchase manager reviews the gap since the store's
// last placed order, which may span multiple days (e.g. reviewing
// Saturday's order on Monday). One grid over both reconciliation views
// (ordered-but-not-received, received-but-not-ordered) anchored to one chosen
// order, plus the store's pending list (dbo.StorePendingOrderItems), with an
// All / Pharma / Non-Pharma filter and Procurement's detail panels for the
// selected row. The PM ticks the not-received products still expected and
// marks them pending; Order Process's "Pending list" compare modes then hold
// those products back (or reduce their qty) until a GRN for them arrives.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from './api/client.js';
import { StoreTrendsPanel } from './storeTrends.jsx';

const VIEWS = [
  { key: 'not_received', label: 'Ordered, not received' },
  { key: 'received', label: 'Received, not ordered' },
  { key: 'pending', label: 'Pending list' },
];
const TYPES = [
  { key: 'all', label: 'All' },
  { key: 'Pharma', label: 'Pharma' },
  { key: 'Non Pharma', label: 'Non-Pharma' },
];
const TREND_FIT = { fetch: 6, min: 4, max: 5 };

function fmtDate(value) {
  if (!value) return '—';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString('en-GB', { day: '2-digit', month: '2-digit', year: '2-digit' });
}

function fmtStamp(value) {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString('en-GB', { day: '2-digit', month: '2-digit', hour: 'numeric', minute: '2-digit', hour12: true })
    .replace(/\b([ap])m\b/gi, (s) => s.toUpperCase());
}

function fmtQty(value) {
  if (value == null || value === '') return '—';
  const n = Number(value);
  return Number.isFinite(n) ? (Number.isInteger(n) ? String(n) : n.toFixed(2)) : '—';
}

function fmtMoney(value) {
  if (value == null || value === '') return '—';
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(2) : '—';
}

const typeLabel = (type) => (type == null ? '—' : type === 'Pharma' ? 'Pharma' : 'Non-Pharma');

// The API lists -> one row shape for the shared grid. Pending rows take their
// type from the not-received line when there is one (the pending table has no
// type); an unknown type passes every type filter.
function gapRows(data) {
  const notReceived = (data?.not_received || []).map((r, i) => ({
    key: `n-${r.product_code}-${i}`, kind: 'not_received',
    code: r.product_code, name: r.product_name, type: r.product_type || 'Pharma',
    qty: r.ordered_qty, date: r.order_date, supplier: r.supplier_name,
    mrp: r.mrp, stock: r.stock, sales: r.sales_90, remarks: r.remarks,
  }));
  const received = (data?.received_not_ordered || []).map((r, i) => ({
    key: `r-${r.grn_no}-${r.product_code}-${i}`, kind: 'received',
    code: r.product_code, name: r.product_name, type: r.product_type || 'Pharma',
    qty: r.qty, free: r.free_qty, date: r.grn_date, supplier: r.supplier_name || r.supplier_code,
    grn: r.grn_no, ptr: r.purchase_price, mrp: r.mrp,
  }));
  const typeByCode = new Map(notReceived.map((r) => [Number(r.code), r.type]));
  const pending = (data?.pending_items || []).map((p) => ({
    key: `p-${p.id}`, kind: 'pending', id: p.id,
    code: p.product_code, name: p.product_name, type: typeByCode.get(Number(p.product_code)) ?? null,
    qty: p.qty, orderId: p.order_id, date: p.flagged_at, by: p.flagged_by, note: p.note,
  }));
  return { notReceived, received, pending };
}

function AddToPendingControl({ row, storeName, orderId, session, onAdded, flagged }) {
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => { setOpen(false); setNote(''); setError(''); }, [row.key]);

  const submit = async () => {
    setBusy(true);
    setError('');
    try {
      const added = await api.legacyAddPendingItem(storeName, {
        product_code: row.code,
        product_name: row.name,
        order_id: orderId,
        qty: row.qty,
        note: note.trim() || undefined,
      }, session);
      onAdded([added]);
      setOpen(false);
      setNote('');
    } catch (err) {
      setError(err.message || 'Could not flag this item.');
    } finally {
      setBusy(false);
    }
  };

  if (flagged) return <span className="ogr-flagged">★ In the pending list</span>;
  if (!open) {
    return <button type="button" className="secondary-button poe-inline-btn" onClick={() => setOpen(true)}>Add to pending</button>;
  }
  return (
    <span className="ogr-add-row">
      <input className="ogr-add-note" placeholder="Note (optional)" value={note} autoFocus
             onChange={(e) => setNote(e.target.value)} disabled={busy}
             onKeyDown={(e) => { if (e.key === 'Enter') submit(); if (e.key === 'Escape') setOpen(false); }} />
      <button type="button" className="primary-button poe-inline-btn" disabled={busy} onClick={submit}>
        {busy ? 'Saving…' : 'Save'}
      </button>
      <button type="button" className="secondary-button poe-inline-btn" disabled={busy} onClick={() => setOpen(false)}>Cancel</button>
      {error && <span className="status-line error">{error}</span>}
    </span>
  );
}

// Right-hand detail: the gap facts for the row, then Procurement's own
// Monthly Trend / Purchase / Sales panels and the All Stores chart.
function GapDetail({ ui, row, store, platformStore, tenantId, session, visibleCodes, orderId, flagged, onAdded, onClear, clearing, onError }) {
  const IntelPanel = ui?.IntelPanel;
  const DocumentCard = ui?.DocumentCard;
  const [record, setRecord] = useState(null);
  if (!row) {
    return <aside className="pw-detail ogr-detail"><span className="ow-side-hint">Select a product to see its trend, purchase &amp; sales.</span></aside>;
  }
  const tile = (label, value, cls) => <div className={cls}><dt>{label}</dt><dd>{value}</dd></div>;
  const kindLabel = { not_received: 'Ordered, not received', received: 'Received, not ordered', pending: 'Pending list' }[row.kind];
  return (
    <aside className="pw-detail ogr-detail" aria-label="Product details">
      <div className="ow-side-panels pw-detail-panels">
        <section className="ow-panel pw-facts-panel">
          <div className="pw-dhead-main">
            <div className="pw-dhead-title">
              <strong title={row.name}>{row.name || `#${row.code}`}</strong>
              <span className="pw-dhead-meta">{[row.code, row.type && typeLabel(row.type), store].filter(Boolean).join(' • ')}</span>
            </div>
            <span className={`ogr-kind ogr-kind--${row.kind}`}>{kindLabel}</span>
            <dl className="pw-facts pw-facts--tiles">
              {row.kind === 'not_received' && (
                <>
                  {tile('Ordered', fmtQty(row.qty))}
                  {tile('Order date', fmtDate(row.date))}
                  {tile('Stock', fmtQty(row.stock), row.stock != null && Number(row.stock) <= 0 ? 'is-zero' : undefined)}
                  {tile('90d sales', fmtQty(row.sales))}
                  {tile('MRP', fmtMoney(row.mrp), 'is-price')}
                </>
              )}
              {row.kind === 'received' && (
                <>
                  {tile('GRN #', row.grn ?? '—')}
                  {tile('GRN date', fmtDate(row.date))}
                  {tile('Received', fmtQty(row.qty))}
                  {tile('Free', fmtQty(row.free))}
                  {tile('PTR', fmtMoney(row.ptr), 'is-price')}
                  {tile('MRP', fmtMoney(row.mrp), 'is-price')}
                </>
              )}
              {row.kind === 'pending' && (
                <>
                  {tile('Pending qty', fmtQty(row.qty))}
                  {tile('Order', row.orderId ?? '—')}
                  {tile('Flagged', fmtStamp(row.date))}
                </>
              )}
            </dl>
            <div className="pw-dhead-facts">
              {row.kind === 'pending' ? (
                <>
                  <span><b>Flagged by</b>{row.by || '—'}</span>
                  {row.note && <span><b>Note</b>{row.note}</span>}
                </>
              ) : (
                <>
                  <span><b>{row.kind === 'not_received' ? 'Order supplier' : 'Supplier'}</b>{row.supplier || '—'}</span>
                  {row.remarks && <span><b>Remarks</b>{row.remarks}</span>}
                </>
              )}
            </div>
            {row.kind === 'not_received' && (
              <div className="ogr-detail-actions">
                <AddToPendingControl row={row} storeName={store} orderId={orderId} session={session}
                                     onAdded={onAdded} flagged={flagged} />
              </div>
            )}
            {row.kind === 'pending' && (
              <div className="ogr-detail-actions">
                <button type="button" className="secondary-button poe-inline-btn" disabled={clearing} onClick={() => onClear([row.id])}>
                  {clearing ? 'Clearing…' : 'Clear from pending list'}
                </button>
              </div>
            )}
          </div>
        </section>
        {IntelPanel && ['trend', 'purchase', 'sales'].map((key) => (
          <IntelPanel key={key} sections={[key]} trendFit={TREND_FIT} store={store} productCode={row.code}
            visibleCodes={visibleCodes} mode="local" session={session} onError={onError}
            onPurchaseSelect={(r) => setRecord({ kind: 'purchase', row: r })}
            onSalesSelect={(r) => setRecord({ kind: 'sales', row: r })} />
        ))}
        <StoreTrendsPanel tenantId={tenantId} storeId={platformStore?.store_id || ''}
          productCode={row.code} session={session} layout="rows" />
      </div>
      {record && DocumentCard && (
        <DocumentCard kind={record.kind} store={store} row={record.row} productCode={row.code} session={session} onClose={() => setRecord(null)} />
      )}
    </aside>
  );
}

export default function OrderGapReview({ session, ui, onOrderEntry }) {
  const [stores, setStores] = useState([]);
  const [storeLabels, setStoreLabels] = useState({});
  const [platformStores, setPlatformStores] = useState([]);
  const [store, setStore] = useState('');
  useEffect(() => {
    if (!store) return;
    try { localStorage.setItem('nexora.desktop.pmOrderStore', store); } catch { /* no storage */ }
  }, [store]);
  const [orderIdInput, setOrderIdInput] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [view, setView] = useState('not_received');
  const [type, setType] = useState('Pharma');
  const [search, setSearch] = useState('');
  const [selectedKey, setSelectedKey] = useState(null);
  const [checked, setChecked] = useState(() => new Set());
  const gridRef = useRef(null);

  useEffect(() => {
    api.legacyStores(session, true)
      .then((rows) => {
        const all = Array.isArray(rows) ? rows : [];
        const list = all.map((r) => r.store_name);
        setStoreLabels(Object.fromEntries(all.map((r) => [r.store_name, r.display_name || r.store_name])));
        setStores(list);
        // Order Entry and Order Gap Review open on the same store (step 1 <-> 2/3).
        let last = '';
        try { last = localStorage.getItem('nexora.desktop.pmOrderStore') || ''; } catch { /* no storage */ }
        setStore((cur) => cur || (list.includes(last) ? last : list[0]) || '');
      })
      .catch((err) => setError(err.message || 'Could not load your stores.'));
    api.listStores(session).then((list) => setPlatformStores(Array.isArray(list) ? list : (list?.items || []))).catch(() => setPlatformStores([]));
  }, [session]);

  const load = useCallback((orderId) => {
    if (!store) return;
    setLoading(true);
    setError('');
    api.legacyGapReview(store, orderId, session)
      .then((result) => {
        setData(result);
        setOrderIdInput(result.order_id != null ? String(result.order_id) : '');
      })
      .catch((err) => setError(err.message || 'Could not load the pending supply review.'))
      .finally(() => setLoading(false));
  }, [session, store]);

  useEffect(() => { setData(null); setSelectedKey(null); setNotice(''); load(undefined); }, [load]);
  useEffect(() => { setChecked(new Set()); }, [view, store, data]);

  const setPending = (items) => setData((prev) => (prev ? { ...prev, pending_items: items } : prev));
  const onAdded = (added) => {
    setData((prev) => {
      if (!prev) return prev;
      const ids = new Set(added.map((a) => a.id));
      return { ...prev, pending_items: [...added, ...(prev.pending_items || []).filter((p) => !ids.has(p.id))] };
    });
  };

  const { notReceived, received, pending } = useMemo(() => gapRows(data), [data]);
  const pendingCodes = useMemo(() => new Set(pending.map((p) => Number(p.code))), [pending]);
  const typeOk = useCallback((r) => type === 'all' || r.type == null || r.type === type, [type]);
  const counts = useMemo(() => ({
    not_received: notReceived.filter(typeOk).length,
    received: received.filter(typeOk).length,
    pending: pending.filter(typeOk).length,
  }), [notReceived, received, pending, typeOk]);
  const rows = useMemo(() => {
    const q = search.trim().toLowerCase();
    const list = view === 'received' ? received : view === 'pending' ? pending : notReceived;
    return list
      .filter(typeOk)
      .filter((r) => !q || String(r.name || '').toLowerCase().includes(q) || String(r.code ?? '').includes(q));
  }, [view, notReceived, received, pending, typeOk, search]);

  // Keep a valid selection: the first visible row when the current one is
  // filtered out (view / type / search change, reload).
  const selected = rows.find((r) => r.key === selectedKey) || null;
  useEffect(() => {
    if (!selected && rows.length) setSelectedKey(rows[0].key);
  }, [selected, rows]);

  const selIndex = selected ? rows.indexOf(selected) : -1;
  const visibleCodes = useMemo(
    () => rows.slice(Math.max(0, selIndex - 3), selIndex + 4).map((r) => r.code).filter((c) => c != null),
    [rows, selIndex],
  );

  // Tick boxes: not-received lines not yet on the pending list, or pending
  // rows (to clear). Received-not-ordered has nothing to act on.
  const checkable = useCallback((r) => (r.kind === 'pending' || (r.kind === 'not_received' && !pendingCodes.has(Number(r.code)))), [pendingCodes]);
  const checkableRows = useMemo(() => rows.filter(checkable), [rows, checkable]);
  const checkedRows = checkableRows.filter((r) => checked.has(r.key));
  const allChecked = checkableRows.length > 0 && checkedRows.length === checkableRows.length;
  const toggle = (key) => setChecked((cur) => {
    const next = new Set(cur);
    if (next.has(key)) next.delete(key); else next.add(key);
    return next;
  });
  const toggleAll = () => setChecked(allChecked ? new Set() : new Set(checkableRows.map((r) => r.key)));

  const markPending = async () => {
    if (!checkedRows.length) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const res = await api.legacyAddPendingItems(store, {
        order_id: data?.order_id,
        items: checkedRows.map((r) => ({ product_code: r.code, product_name: r.name, qty: r.qty })),
      }, session);
      setPending(res.pending_items || []);
      setNotice(`${res.added} product${res.added === 1 ? '' : 's'} added to the pending list${res.updated ? `, ${res.updated} refreshed` : ''}.`);
    } catch (err) {
      setError(err.message || 'Could not update the pending list.');
    } finally {
      setBusy(false);
    }
  };

  // Order Entry step 1: sign off the current order's review.
  const review = data?.review;
  const reviewable = Boolean(review?.required && data?.order_id === review.order_id);
  const completeReview = async () => {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const status = await api.legacyCompleteGapReview(store, { order_id: data?.order_id, not_received: notReceived.length }, session);
      setData((prev) => (prev ? { ...prev, review: status } : prev));
      setNotice('Review done -- Purchase Entry Complete can now process the next order.');
    } catch (err) {
      setError(err.message || 'Could not save the review.');
    } finally {
      setBusy(false);
    }
  };

  const clearPending = async (ids) => {
    if (!ids.length) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const res = await api.legacyClearPendingItems(store, ids, session);
      const gone = new Set(ids);
      setPending((data?.pending_items || []).filter((p) => !gone.has(p.id)));
      setNotice(`${res.cleared} product${res.cleared === 1 ? '' : 's'} cleared from the pending list.`);
    } catch (err) {
      setError(err.message || 'Could not clear the pending list.');
    } finally {
      setBusy(false);
    }
  };

  const onGridKey = (e) => {
    if (e.key === ' ' && selected && checkable(selected)) {
      e.preventDefault();
      toggle(selected.key);
      return;
    }
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
    e.preventDefault();
    const next = rows[Math.min(rows.length - 1, Math.max(0, selIndex + (e.key === 'ArrowDown' ? 1 : -1)))];
    if (next) setSelectedKey(next.key);
  };
  useEffect(() => {
    gridRef.current?.querySelector('tr.is-sel')?.scrollIntoView({ block: 'nearest' });
  }, [selectedKey]);

  const platformStore = platformStores.find((s) => String(s.store_code || '').toUpperCase() === String(store).toUpperCase()) || null;
  const tenantId = platformStore?.tenant_id || session?.user?.tenant_id || '';
  const hasChecks = view !== 'received';
  const cols = view === 'received' ? 9 : view === 'pending' ? 8 : 9;

  return (
    <section className="screen-panel poe-screen ogr-screen">
      <header className="screen-header">
        <div>
          <h2>Pending Supply Review</h2>
          <p>Review what was ordered but never arrived, and mark the products still expected as pending -- Order Process's pending-list compare holds them back until they arrive.</p>
        </div>
        <div className="poe-tools">
          {stores.length > 1 && (
            <select aria-label="Store" value={store} onChange={(e) => setStore(e.target.value)}>
              {stores.map((s) => <option key={s} value={s}>{storeLabels[s] || s}</option>)}
            </select>
          )}
        </div>
      </header>

      {error && <div className="status-line error">{error}</div>}
      {notice && <div className="status-line ok">{notice}</div>}

      {reviewable && (
        <div className={`ogr-review${review.done ? ' is-done' : ''}`}>
          <span className="ogr-review-step">Purchase Entry Complete · step 1</span>
          {review.done ? (
            <span>✓ Order <b>#{review.order_id}</b> reviewed{review.reviewed_by ? ` by ${review.reviewed_by}` : ''} · {fmtStamp(review.reviewed_at)}</span>
          ) : (
            <span>Tick the products still expected under “Ordered, not received”, <b>Mark pending</b>, then <b>Review done</b>.</span>
          )}
          <span className="ogr-review-actions">
            {review.done ? (
              <button type="button" className="secondary-button poe-inline-btn" disabled={busy} onClick={completeReview}
                      title="Record this review again (e.g. after changing the pending list)">Review again</button>
            ) : (
              <button type="button" className="primary-button poe-inline-btn" disabled={busy || loading} onClick={completeReview}>✓ Review done</button>
            )}
            {review.done && onOrderEntry && (
              <button type="button" className="primary-button poe-inline-btn" onClick={onOrderEntry}>Go to Purchase Entry Complete →</button>
            )}
          </span>
        </div>
      )}

      <div className="ogr-toolbar">
        <span className="pw-seg" role="tablist" aria-label="Gap">
          {VIEWS.map((v) => (
            <button key={v.key} type="button" role="tab" aria-selected={view === v.key}
                    className={view === v.key ? 'active' : undefined} onClick={() => setView(v.key)}>
              {v.label}<span className="pw-seg-count">{loading && !data ? '…' : counts[v.key]}</span>
            </button>
          ))}
        </span>
        <span className="pw-seg" role="radiogroup" aria-label="Product type">
          {TYPES.map((t) => (
            <button key={t.key} type="button" role="radio" aria-checked={type === t.key}
                    className={type === t.key ? 'active' : undefined} onClick={() => setType(t.key)}>
              {t.label}
            </button>
          ))}
        </span>
        <input className="ogr-search" type="search" placeholder="Search product…" value={search}
               onChange={(e) => setSearch(e.target.value)} aria-label="Search product" />
        {view === 'not_received' && (
          <button type="button" className="primary-button" disabled={busy || !checkedRows.length} onClick={markPending}
                  title="Add the ticked products to the store's pending list">
            {busy ? 'Saving…' : `Mark pending${checkedRows.length ? ` (${checkedRows.length})` : ''}`}
          </button>
        )}
        {view === 'pending' && (
          <button type="button" className="secondary-button" disabled={busy || !checkedRows.length}
                  onClick={() => clearPending(checkedRows.map((r) => r.id))}>
            {busy ? 'Clearing…' : `Clear${checkedRows.length ? ` (${checkedRows.length})` : ''}`}
          </button>
        )}
        <span className="ogr-order">
          {data?.order_id
            ? <>Since order <b>#{data.order_id}</b> · {fmtStamp(data.order_date)}</>
            : <span className="poe-muted">{loading ? 'Loading…' : 'No previous order to compare against.'}</span>}
        </span>
        <input className="ogr-order-input" type="number" placeholder="Order ID" value={orderIdInput}
               onChange={(e) => setOrderIdInput(e.target.value)}
               onKeyDown={(e) => { if (e.key === 'Enter' && orderIdInput) load(Number(orderIdInput)); }} />
        <button type="button" className="secondary-button" disabled={loading || !orderIdInput}
                onClick={() => load(Number(orderIdInput))}>Review order</button>
        <button type="button" className="secondary-button" disabled={loading} onClick={() => load(undefined)}
                title="Reload the latest previous order">{loading ? 'Loading…' : '⟳ Refresh'}</button>
      </div>

      <div className="ogr-body">
        <div className="ogr-gridwrap" ref={gridRef} tabIndex={0} onKeyDown={onGridKey}>
          <table className="trp-table ogr-table">
            <thead>
              <tr>
                {hasChecks && (
                  <th className="ogr-check">
                    <input type="checkbox" aria-label="Tick all" checked={allChecked} disabled={!checkableRows.length} onChange={toggleAll} />
                  </th>
                )}
                <th className="trp-left">Product</th><th className="trp-left">Type</th>
                {view === 'received' && (<><th>Qty</th><th>Free</th><th>GRN#</th><th>GRN date</th><th className="trp-left">Supplier</th><th>PTR</th><th>MRP</th></>)}
                {view === 'not_received' && (<><th>Ordered</th><th>Order date</th><th>Stock</th><th>90d sales</th><th className="trp-left">Order supplier</th><th>MRP</th></>)}
                {view === 'pending' && (<><th>Pending qty</th><th>Order</th><th>Flagged</th><th className="trp-left">By</th><th className="trp-left">Note</th></>)}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const onList = r.kind === 'not_received' && pendingCodes.has(Number(r.code));
                return (
                  <tr key={r.key} className={r.key === selectedKey ? 'is-sel' : undefined} onClick={() => setSelectedKey(r.key)}>
                    {hasChecks && (
                      <td className="ogr-check" onClick={(e) => e.stopPropagation()}>
                        {onList
                          ? <span className="ogr-star" title="Already in the pending list">★</span>
                          : <input type="checkbox" aria-label="Tick" checked={checked.has(r.key)} onChange={() => toggle(r.key)} />}
                      </td>
                    )}
                    <td className="trp-left ogr-name" title={r.name}>{r.name || `#${r.code}`}</td>
                    <td className="trp-left"><span className={`ogr-type${r.type && r.type !== 'Pharma' ? ' ogr-type--np' : ''}`}>{typeLabel(r.type)}</span></td>
                    {r.kind === 'received' && (
                      <>
                        <td>{fmtQty(r.qty)}</td>
                        <td>{r.free ? fmtQty(r.free) : '—'}</td>
                        <td>{r.grn ?? '—'}</td>
                        <td>{fmtDate(r.date)}</td>
                        <td className="trp-left ogr-ellipsis" title={r.supplier || ''}>{r.supplier || '—'}</td>
                        <td>{fmtMoney(r.ptr)}</td>
                        <td>{fmtMoney(r.mrp)}</td>
                      </>
                    )}
                    {r.kind === 'not_received' && (
                      <>
                        <td>{fmtQty(r.qty)}</td>
                        <td>{fmtDate(r.date)}</td>
                        <td className={r.stock != null && Number(r.stock) <= 0 ? 'ogr-zero' : undefined}>{fmtQty(r.stock)}</td>
                        <td>{fmtQty(r.sales)}</td>
                        <td className="trp-left ogr-ellipsis" title={r.supplier || ''}>{r.supplier || '—'}</td>
                        <td>{fmtMoney(r.mrp)}</td>
                      </>
                    )}
                    {r.kind === 'pending' && (
                      <>
                        <td>{fmtQty(r.qty)}</td>
                        <td>{r.orderId ?? '—'}</td>
                        <td>{fmtStamp(r.date)}</td>
                        <td className="trp-left">{r.by || '—'}</td>
                        <td className="trp-left ogr-ellipsis" title={r.note || ''}>{r.note || '—'}</td>
                      </>
                    )}
                  </tr>
                );
              })}
              {!rows.length && (
                <tr>
                  <td colSpan={cols} className="poe-muted ogr-empty">
                    {loading ? 'Loading…'
                      : view === 'pending' ? 'The pending list is empty. Tick products under “Ordered, not received” and Mark pending.'
                        : !data?.order_id ? 'No previous order to compare against.'
                          : view === 'received' ? 'Nothing received off-order.' : 'Nothing outstanding.'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <GapDetail ui={ui} row={selected} store={store} platformStore={platformStore} tenantId={tenantId}
                   session={session} visibleCodes={visibleCodes} orderId={data?.order_id}
                   flagged={selected ? pendingCodes.has(Number(selected.code)) : false}
                   onAdded={onAdded} onClear={clearPending} clearing={busy} onError={setError} />
      </div>
      <div className="ogr-foot poe-muted">
        {rows.length} line{rows.length === 1 ? '' : 's'}{type !== 'all' ? ` · ${typeLabel(type)}` : ''}
        {hasChecks && checkedRows.length ? ` · ${checkedRows.length} ticked` : ''} · ↑/↓ move · Space tick
      </div>
    </section>
  );
}
