// Order Entry -- a purchase manager starts Order Process for their own store
// (owner rulings 2026-11-05). They type the store's last bill + last GRN off
// the POS and pick the order type (Regular compares with earlier orders, WH
// does not). The server syncs, checks both numbers reached OrderNMC, then
// generates the order. An order left open from an earlier day must be
// reviewed and Finalized in the Order Workspace first.
//
// Below it: stock received on supplier GRNs since the previous active day's
// first order for products the app never put on an order.
import { useCallback, useEffect, useState } from 'react';
import { api } from './api/client.js';

const POLL_MS = 3000;
const TYPES = [['pharma', 'Pharma'], ['non_pharma', 'Non Pharma'], ['all', 'All']];

function fmtStamp(value) {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString('en-GB', { day: '2-digit', month: '2-digit', hour: 'numeric', minute: '2-digit', hour12: true })
    .replace(/\b([ap])m\b/gi, (s) => s.toUpperCase());
}

function fmtDate(value) {
  if (!value) return '—';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString('en-GB', { day: '2-digit', month: '2-digit' });
}

const STATUS_LABEL = {
  QTY_REVIEW: 'Qty review pending', SUPPLIER_ASSIGNMENT: 'Supplier assignment pending',
  READY: 'Ready to finalize', FINALIZED: 'Finalized', DRAFT: 'Draft',
};

function ReceivedNotOrdered({ session, store }) {
  const [type, setType] = useState('pharma');
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const load = useCallback(() => {
    if (!store) return;
    setLoading(true);
    setError('');
    api.legacyReceivedNotOrdered(store, type, session)
      .then(setData)
      .catch((err) => setError(err.message || 'Could not load the report.'))
      .finally(() => setLoading(false));
  }, [session, store, type]);

  useEffect(() => { load(); }, [load]);

  const rows = data?.rows || [];
  return (
    <section className="poe-card">
      <header className="poe-card-head">
        <h3>Received, not ordered by the app</h3>
        <span className="poe-muted">Supplier GRNs since {fmtStamp(data?.since)} for products on none of the app's orders · as of the last sync</span>
        <div className="poe-tools">
          <select aria-label="Product type" value={type} onChange={(e) => setType(e.target.value)}>
            {TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <button type="button" className="secondary-button" onClick={load} disabled={loading}>{loading ? 'Loading…' : 'Refresh'}</button>
        </div>
      </header>
      {error && <div className="status-line error">{error}</div>}
      <div className="trp-tablewrap poe-tablewrap">
        <table className="trp-table">
          <thead>
            <tr>
              <th>GRN</th><th>Date</th><th className="trp-left">Supplier</th><th>Code</th>
              <th className="trp-left">Product</th><th>Qty</th><th>Free</th><th>PTR</th><th>MRP</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={`${r.grn_no}-${r.product_code}-${i}`}>
                <td>{r.grn_no}</td><td>{fmtDate(r.grn_date)}</td>
                <td className="trp-left">{r.supplier_name || r.supplier_code || '—'}</td>
                <td>{r.product_code}</td><td className="trp-left">{r.product_name || '—'}</td>
                <td>{r.qty}</td><td>{r.free_qty || ''}</td>
                <td>{r.purchase_price.toFixed(2)}</td><td>{r.mrp.toFixed(2)}</td>
              </tr>
            ))}
            {!loading && !rows.length && <tr><td colSpan={9} className="poe-muted">Nothing received outside the app's orders.</td></tr>}
          </tbody>
        </table>
      </div>
      <div className="poe-muted">{rows.length} line{rows.length === 1 ? '' : 's'}</div>
    </section>
  );
}

export default function PmOrderEntry({ session, onOpenWorkspace }) {
  const [stores, setStores] = useState([]);
  const [store, setStore] = useState('');
  const [state, setState] = useState(null);
  const [lastBill, setLastBill] = useState('');
  const [lastGrn, setLastGrn] = useState('');
  const [orderType, setOrderType] = useState('REGULAR');
  const [warning, setWarning] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.legacyStores(session, true)
      .then((rows) => {
        const list = (Array.isArray(rows) ? rows : []).map((r) => r.store_name);
        setStores(list);
        setStore((cur) => cur || list[0] || '');
      })
      .catch((err) => setError(err.message || 'Could not load your stores.'));
  }, [session]);

  const refresh = useCallback(() => {
    if (!store) return Promise.resolve();
    return api.legacyOrderEntry(store, session).then(setState).catch((err) => setError(err.message));
  }, [session, store]);

  useEffect(() => { setState(null); refresh(); }, [refresh]);

  const running = state?.job?.status === 'running';
  useEffect(() => {
    if (!running) return undefined;
    const t = setInterval(refresh, POLL_MS);
    return () => clearInterval(t);
  }, [running, refresh]);

  // Fresh numbers for the next order once this one completes.
  const lastJobId = state?.job?.job_id;
  const lastJobStatus = state?.job?.status;
  useEffect(() => {
    if (lastJobStatus === 'completed') { setLastBill(''); setLastGrn(''); setOrderType('REGULAR'); }
  }, [lastJobId, lastJobStatus]);

  const submit = async (confirmed = false) => {
    setBusy(true);
    setError('');
    setWarning('');
    try {
      await api.legacyPmStartOrder(store, { last_bill: lastBill.trim(), last_grn: lastGrn.trim(), order_type: orderType, confirmed }, session);
      await refresh();
    } catch (err) {
      const message = err.message || 'Could not start the order.';
      if (/pending supplier assignment|confirm order & process/i.test(message) && !confirmed) setWarning(message);
      else setError(message);
    } finally {
      setBusy(false);
    }
  };

  const order = state?.latest_order;
  const job = state?.job;
  const canSubmit = store && lastBill.trim() && lastGrn.trim() && !state?.blocked && !running && !busy;

  return (
    <section className="screen-panel poe-screen">
      <header className="screen-header">
        <div>
          <h2>Order Entry</h2>
          <p>Enter the store's last bill and last GRN to sync and generate the order.</p>
        </div>
        {stores.length > 1 && (
          <select aria-label="Store" value={store} onChange={(e) => setStore(e.target.value)}>
            {stores.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        )}
      </header>

      {error && <div className="status-line error">{error}</div>}

      <div className="poe-grid">
        <section className="poe-card">
          <header className="poe-card-head"><h3>Current order · {store || '—'}</h3></header>
          {order?.order_id ? (
            <dl className="poe-meta">
              <div><dt>Order</dt><dd>#{order.order_no ?? order.order_id} · {fmtStamp(state?.header?.order_datetime)}</dd></div>
              <div><dt>Status</dt><dd className={order.status === 'FINALIZED' ? 'lgo-ok' : 'lgo-warn'}>{STATUS_LABEL[order.status] || order.status}</dd></div>
              <div><dt>Qty review pending</dt><dd>{order.qty_pending}</dd></div>
              <div><dt>Unassigned</dt><dd>{order.unassigned_lines}</dd></div>
              <div><dt>Last bill / GRN</dt><dd>{state?.header?.last_sale_bill_no || '—'} / {state?.header?.last_grn || '—'}</dd></div>
            </dl>
          ) : <p className="poe-muted">No order yet.</p>}
          {state?.blocked && (
            <div className="status-line error">
              This order is from an earlier day and is not finalized. Review the pending products and Finalize it in the Order Workspace before generating today's order.
              {onOpenWorkspace && <button type="button" className="secondary-button poe-inline-btn" onClick={onOpenWorkspace}>Open Order Workspace</button>}
            </div>
          )}
        </section>

        <section className="poe-card">
          <header className="poe-card-head"><h3>New order</h3></header>
          <div className="poe-form">
            <label><span>Last bill</span>
              <input value={lastBill} placeholder="C01042645" disabled={running}
                onChange={(e) => setLastBill(e.target.value.replace(/\s/g, '').toUpperCase())} />
            </label>
            <label><span>Last GRN (supplier)</span>
              <input value={lastGrn} placeholder="2742" inputMode="numeric" disabled={running}
                onChange={(e) => setLastGrn(e.target.value.replace(/\D/g, ''))} />
            </label>
            <label><span>Order type</span>
              <select value={orderType} disabled={running} onChange={(e) => setOrderType(e.target.value)}>
                <option value="REGULAR">Regular (compare with earlier orders)</option>
                <option value="WH">WH (no compare)</option>
              </select>
            </label>
          </div>
          {warning ? (
            <div className="status-line poe-warn">
              {warning}
              <button type="button" className="primary-button poe-inline-btn" disabled={busy} onClick={() => submit(true)}>Continue &amp; Process</button>
            </div>
          ) : (
            <button type="button" className="primary-button" disabled={!canSubmit} onClick={() => submit(false)}>
              {running ? 'Processing…' : busy ? 'Starting…' : 'Sync & Generate Order'}
            </button>
          )}
          {job && (
            <div className="poe-job">
              <div className={job.status === 'completed' ? 'lgo-ok' : job.status === 'failed' ? 'lgo-bad' : 'lgo-run'}>
                {job.status === 'running' ? 'Running: ' : job.status === 'completed' ? '✓ ' : '✗ '}{job.error || job.message}
              </div>
              <div className="poe-log">
                {(job.log || []).slice(-8).map((line, i) => (
                  <div key={i}><span className="poe-muted">{fmtStamp(line.at)}</span> {line.message}</div>
                ))}
              </div>
            </div>
          )}
        </section>
      </div>

      <ReceivedNotOrdered session={session} store={store} />
    </section>
  );
}
