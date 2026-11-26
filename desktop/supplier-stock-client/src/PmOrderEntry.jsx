// Order Entry -- a purchase manager reviews two plain "most recent" grids
// (GRNs + sale bills) against their own paperwork, then clicks ONE Submit
// button (owner ruling 2026-11-24). No order-type choice, no automation
// button/panel, and no job-log detail on this screen -- the PM must never
// see or infer that an automated background process exists. Automation
// settings now live on the admin-only OrderAutomationSettings screen.
import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from './api/client.js';
import OrderEntrySync from './orderEntrySync.jsx';

const POLL_MS = 3000;

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

function fmtGrnDateTime(date, time) {
  const datePart = fmtDate(date);
  if (!time) return datePart;
  const timePart = fmtStamp(time).replace(/^\d{2}\/\d{2}\s*/, '');
  return `${datePart} ${timePart}`;
}

// Two plain verification grids -- most recent GRNs and most recent sale
// bills, newest first, no exclusion filtering. Replaces the old "received,
// not ordered" report, which deliberately EXCLUDED GRNs whose product ended
// up on an order and so legitimately disagreed with the Current Order
// card's own Last GRN -- confusing the PM. Top row of each is auto-used.
function RecentVerificationGrids({ session, store, onTopRow, reloadToken, syncing }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const storeRef = useRef(store);
  storeRef.current = store;

  // Clear the grids the instant the store changes, instead of leaving the
  // previous store's rows (and its "will be used" top row) on screen until
  // the new fetch resolves -- a stale GRN/bill list under a different
  // store name is actively misleading, not just a cosmetic lag.
  useEffect(() => {
    setData(null);
    onTopRow(null, null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [store]);

  const load = useCallback(() => {
    // While the store's sync runs, the rows here would be the pre-sync ones
    // -- not what the PM is verifying against. Load once the sync is done
    // (reloadToken bumps then).
    if (!store || syncing) return;
    const requestedStore = store;
    setLoading(true);
    setError('');
    api.legacyOrderEntryRecent(store, session)
      .then((result) => {
        // The store may have changed again while this request was in
        // flight; a late response for an old store must not clobber the
        // grids the PM is now looking at.
        if (requestedStore !== storeRef.current) return;
        setData(result);
        onTopRow(result.bills?.[0]?.bill_no ?? null, result.grns?.[0] ? String(result.grns[0].grn_no) : null);
      })
      .catch((err) => setError(err.message || 'Could not load the recent GRN/bill grids.'))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session, store, syncing]);

  // reloadToken bumps once a triggered sync has finished, so the grids pick
  // up the freshly-synced GRN/bill rows without the PM doing anything else.
  useEffect(() => { load(); }, [load, reloadToken]);

  const grns = syncing ? [] : data?.grns || [];
  const bills = syncing ? [] : data?.bills || [];
  const waitRow = (span) => (syncing || (loading && !data)
    ? <tr><td colSpan={span} className="poe-muted">{syncing ? 'Waiting for the sync to finish…' : 'Loading…'}</td></tr>
    : null);

  return (
    <div className="poe-grid">
      <section className="poe-card">
        <header className="poe-card-head">
          <h3>Recent GRNs</h3>
          <span className="poe-muted">Most recent supplier GRNs · as of the last sync</span>
          <div className="poe-tools">
            <button type="button" className="secondary-button" onClick={load} disabled={loading || syncing}>{loading ? 'Loading…' : 'Refresh'}</button>
          </div>
        </header>
        {error && <div className="status-line error">{error}</div>}
        <div className="trp-tablewrap poe-tablewrap">
          <table className="trp-table">
            <thead>
              <tr>
                <th>GRN#</th>
                <th title="Real GRN entry time at the branch. Time blank until backfilled or re-synced.">Date / time</th>
                <th className="trp-left">Supplier</th>
                <th>Items</th><th>Total qty</th>
              </tr>
            </thead>
            <tbody>
              {grns.map((r, i) => (
                <tr key={`${r.grn_no}-${i}`} className={i === 0 ? 'poe-top-row' : undefined}>
                  <td>{r.grn_no}{i === 0 && <span className="poe-top-badge">Will be used</span>}</td>
                  <td>{fmtGrnDateTime(r.grn_date, r.grn_time)}</td>
                  <td className="trp-left">{r.supplier_name || r.supplier_code || '—'}</td>
                  <td>{r.item_count}</td>
                  <td>{r.total_qty}</td>
                </tr>
              ))}
              {waitRow(5)}
              {!loading && !syncing && data && !grns.length && <tr><td colSpan={5} className="poe-muted">No GRNs found.</td></tr>}
            </tbody>
          </table>
        </div>
        <div className="poe-muted">{grns.length} GRN{grns.length === 1 ? '' : 's'}</div>
      </section>

      <section className="poe-card">
        <header className="poe-card-head">
          <h3>Recent sale bills</h3>
          <span className="poe-muted">Most recent sale bills · as of the last sync</span>
        </header>
        <div className="trp-tablewrap poe-tablewrap">
          <table className="trp-table">
            <thead>
              <tr><th>Bill#</th><th>Date / time</th><th className="trp-left">Salesman</th><th className="trp-left">Customer</th><th>Amount</th></tr>
            </thead>
            <tbody>
              {bills.map((r, i) => (
                <tr key={`${r.bill_no}-${i}`} className={i === 0 ? 'poe-top-row' : undefined}>
                  <td>{r.bill_no || '—'}{i === 0 && <span className="poe-top-badge">Will be used</span>}</td>
                  <td>{fmtStamp(r.bill_date)}</td>
                  <td className="trp-left">{r.salesman || '—'}</td>
                  <td className="trp-left">{r.customer || '—'}</td>
                  <td>{r.amount.toFixed(2)}</td>
                </tr>
              ))}
              {waitRow(5)}
              {!loading && !syncing && data && !bills.length && <tr><td colSpan={5} className="poe-muted">No sale bills found.</td></tr>}
            </tbody>
          </table>
        </div>
        <div className="poe-muted">{bills.length} line{bills.length === 1 ? '' : 's'}</div>
      </section>
    </div>
  );
}

function fmtLogStamp(d) {
  return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

export default function PmOrderEntry({ session, onOpenGapReview }) {
  const [stores, setStores] = useState([]);
  const [storeLabels, setStoreLabels] = useState({});
  const [lastSync, setLastSync] = useState({});
  const [store, setStore] = useState('');
  useEffect(() => {
    if (!store) return;
    try { localStorage.setItem('nexora.desktop.pmOrderStore', store); } catch { /* no storage */ }
  }, [store]);
  const [state, setState] = useState(null);
  // Auto-filled from the top row of the recent-GRN / recent-bill grids --
  // the PM never types these.
  const [topBill, setTopBill] = useState(null);
  const [topGrn, setTopGrn] = useState(null);
  const [warning, setWarning] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [queue, setQueue] = useState(null);
  const [syncing, setSyncing] = useState(false);
  const [syncNote, setSyncNote] = useState('');
  const [syncProgress, setSyncProgress] = useState(0);
  const [syncLog, setSyncLog] = useState([]);
  // 'running' | 'failed' | 'done' -- the sync view stays up on a failure
  // (with Retry) and gives way to the order card + grids once it is done.
  const [syncStatus, setSyncStatus] = useState('idle');
  const [syncStartedAt, setSyncStartedAt] = useState(0);
  const [reloadToken, setReloadToken] = useState(0);
  // The store whose sync is on screen. The picker is locked while a sync
  // runs, and a loop that finds the store changed under it stops writing to
  // this screen (its server-side job still finishes on its own).
  const storeRef = useRef(store);
  storeRef.current = store;

  // Re-run on mount, and again any time the real Stores.LastSyncTime may have
  // changed (after a sync finishes) -- the label always reflects the DB, not
  // an optimistic client-clock guess.
  const loadStores = useCallback(() => {
    return api.legacyStores(session, true)
      .then((rows) => {
        const all = Array.isArray(rows) ? rows : [];
        const list = all.map((r) => r.store_name);
        setStoreLabels(Object.fromEntries(all.map((r) => [r.store_name, r.display_name || r.store_name])));
        setLastSync(Object.fromEntries(all.map((r) => [r.store_name, r.last_sync_time])));
        setStores(list);
        // Order Entry and Order Gap Review open on the same store (step 1 <-> 2/3).
        let last = '';
        try { last = localStorage.getItem('nexora.desktop.pmOrderStore') || ''; } catch { /* no storage */ }
        setStore((cur) => cur || (list.includes(last) ? last : list[0]) || '');
      })
      .catch((err) => setError(err.message || 'Could not load your stores.'));
  }, [session]);

  useEffect(() => { loadStores(); }, [loadStores]);

  // Trigger this module's own branch/agent -> central OrderNMC sync job
  // (POST /sync, the same one "Sync" in the legacy Order Workspace starts --
  // NOT the unrelated platform sync.* pipeline, which has its own separate
  // store registry and never touches OrderNMC.Stores.LastSyncTime), then
  // poll the job until it finishes, then reload the two grids -- "connect
  // and load GRN and sales after sync" (owner spec, 2026-11-24). Runs once
  // on store load, and again any time the PM hits Fetch Data.
  const runSync = useCallback(async () => {
    if (!store) return;
    const syncStore = store;
    const stale = () => storeRef.current !== syncStore;
    setSyncing(true);
    setSyncStatus('running');
    setSyncStartedAt(Date.now());
    setSyncNote('Connecting to store…');
    setSyncProgress(5);
    setSyncLog([{ stamp: fmtLogStamp(new Date()), text: 'Sync requested for ' + (storeLabels[store] || store) }]);
    setError('');
    let loggedCount = 0;
    try {
      const started = await api.legacyStartSync(store, session);
      const jobId = started?.job_id;
      if (!jobId) throw new Error('Sync did not return a job id.');
      const deadline = Date.now() + 10 * 60 * 1000;
      // eslint-disable-next-line no-constant-condition
      while (true) {
        await new Promise((r) => setTimeout(r, 2000));
        if (stale()) return;
        const job = await api.legacyJob(jobId, session).catch(() => null);
        if (!job) continue;
        const total = job.total_steps || 1;
        setSyncProgress(Math.max(5, Math.min(99, Math.round(((job.step || 0) / total) * 100))));
        setSyncNote(job.message || 'Syncing…');
        const newLines = (job.log || []).slice(loggedCount);
        if (newLines.length) {
          loggedCount = job.log.length;
          setSyncLog((log) => [...log, ...newLines.map((l) => ({ stamp: fmtLogStamp(new Date(l.at)), text: l.message }))]);
        }
        if (job.status === 'completed' || job.status === 'failed' || Date.now() > deadline) {
          if (job.status === 'failed') throw new Error(job.error || 'Sync failed.');
          break;
        }
      }
      if (stale()) return;
      setSyncProgress(100);
      setSyncNote('');
      setSyncLog((log) => [...log, { stamp: fmtLogStamp(new Date()), text: 'Sync complete. Order DB is up to date.' }]);
      setSyncStatus('done');
      setReloadToken((t) => t + 1);
    } catch (err) {
      if (stale()) return;
      setSyncNote('');
      setSyncLog((log) => [...log, { stamp: fmtLogStamp(new Date()), text: `Sync failed: ${err.message || 'unknown error'}` }]);
      setError(err.message || 'Sync could not be started.');
      setSyncStatus('failed');
      // Still show what the Order DB has, with the error above it.
      setReloadToken((t) => t + 1);
    } finally {
      // Re-read the real Stores.LastSyncTime -- mark_sync_result runs on
      // both success and failure, so refresh the label either way instead
      // of trusting the browser clock.
      loadStores();
      if (!stale()) setSyncing(false);
    }
  }, [session, store, storeLabels, loadStores]);

  useEffect(() => {
    if (store) runSync();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [store]);

  const refresh = useCallback(() => {
    if (!store) return Promise.resolve();
    return api.legacyOrderEntry(store, session).then(setState).catch((err) => setError(err.message));
  }, [session, store]);

  const refreshQueue = useCallback(() => {
    if (!store) return Promise.resolve();
    return api.legacyOrderEntryQueue(store, session).then(setQueue).catch(() => {});
  }, [session, store]);

  useEffect(() => { setState(null); setQueue(null); refresh(); refreshQueue(); }, [refresh, refreshQueue]);
  // The sync can change the Current Order card too (header, pending counts).
  useEffect(() => { if (reloadToken) refresh(); }, [reloadToken, refresh]);

  const queuePending = queue?.status === 'PENDING' || queue?.status === 'RUNNING';
  const running = state?.job?.status === 'running' || queuePending;
  useEffect(() => {
    if (!running) return undefined;
    const t = setInterval(() => { refresh(); refreshQueue(); }, POLL_MS);
    return () => clearInterval(t);
  }, [running, refresh, refreshQueue]);

  // Once the submit (queued or direct) finishes, refresh the Current Order
  // card with fresh real numbers. No log lines, no "queued (auto)" text --
  // the PM only ever sees idle / submitted / done on this screen.
  const lastQueueId = queue?.queue_id;
  const lastQueueStatus = queue?.status;
  useEffect(() => {
    if (lastQueueStatus === 'DONE') refresh();
  }, [lastQueueId, lastQueueStatus, refresh]);

  const submit = async (confirmed = false) => {
    if (!topBill || !topGrn) return;
    setBusy(true);
    setError('');
    setWarning('');
    try {
      const result = await api.legacyPmStartOrder(store, {
        last_bill: topBill, last_grn: topGrn,
        order_type: 'REGULAR', // order type is now a store-level admin setting, not a per-submit PM choice
        confirmed,
      }, session);
      if (result?.queued) setQueue(result);
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
  // Order Entry runs Review pending -> Fetch data / last bill + GRN -> Process
  // order; the server refuses the submit until step 1 is done too.
  const gap = state?.gap_review;
  const gapOk = !gap?.required || gap?.done;
  const billsOk = Boolean(topBill && topGrn);
  const canSubmit = store && billsOk && gapOk && !state?.blocked && !running && !busy && !syncing;
  const submitHint = !gapOk ? 'Review the pending products first (step 1).'
    : state?.blocked ? 'The current order must be finalized in Procurement first.' : undefined;
  const simpleStatus = running || busy ? 'submitted' : 'idle';

  return (
    <section className="screen-panel poe-screen">
      <header className="screen-header">
        <div>
          <h2>Purchase Entry Complete</h2>
          <p>Review the recent GRNs and sale bills below against your paperwork, then submit.</p>
        </div>
        <div className="poe-tools">
          {stores.length > 1 && (
            <select aria-label="Store" value={store} disabled={syncing}
              title={syncing ? 'Wait for this store’s sync to finish before switching' : undefined}
              onChange={(e) => setStore(e.target.value)}>
              {stores.map((s) => <option key={s} value={s}>{storeLabels[s] || s}</option>)}
            </select>
          )}
          <span className="poe-muted poe-last-sync">Last sync: {fmtStamp(lastSync[store])}</span>
          <button type="button" className="primary-button" disabled={syncing || !store} onClick={runSync}>
            {syncing ? 'Fetching…' : 'Fetch Data'}
          </button>
        </div>
      </header>

      {error && <div className="status-line error">{error}</div>}

      {store && (
        <ol className="oe-steps" aria-label="Purchase Entry Complete steps">
          <li className={!state ? 'is-wait' : gapOk ? 'is-done' : 'is-now'}>
            <span className="oe-step-no">{gapOk && state ? '✓' : '1'}</span>
            <div className="oe-step-text">
              <b>Pending Supply Review</b>
              <span>
                {!state ? 'Checking…'
                  : !gap?.required ? 'No previous order to review.'
                    : gap.done ? `Order #${gap.order_id} reviewed${gap.reviewed_by ? ` by ${gap.reviewed_by}` : ''} · ${fmtStamp(gap.reviewed_at)}`
                      : `Order #${gap.order_id}: mark the products still expected as pending, then Review done.`}
              </span>
            </div>
            {state && gap?.required && onOpenGapReview && (
              <button type="button" className={gap.done ? 'secondary-button poe-inline-btn' : 'primary-button poe-inline-btn'} onClick={onOpenGapReview}>
                {gap.done ? 'Open review' : 'Open Pending Supply Review'}
              </button>
            )}
          </li>
          <li className={syncing ? 'is-now' : billsOk ? 'is-done' : gapOk ? 'is-now' : 'is-wait'}>
            <span className="oe-step-no">{billsOk && !syncing ? '✓' : '2'}</span>
            <div className="oe-step-text">
              <b>Fetch data · last bill / GRN</b>
              <span>{syncing ? 'Syncing the store…' : billsOk ? `${topBill} / ${topGrn}` : 'Fetch Data, then check the bills and GRNs below.'}</span>
            </div>
          </li>
          <li className={running || busy ? 'is-now' : canSubmit ? 'is-now' : 'is-wait'}>
            <span className="oe-step-no">3</span>
            <div className="oe-step-text">
              <b>Process order</b>
              <span>{running || busy ? 'Processing…' : canSubmit ? 'Ready -- press Submit.' : 'After steps 1 and 2.'}</span>
            </div>
          </li>
        </ol>
      )}

      {(syncing || syncStatus === 'failed') && (
        <OrderEntrySync
          storeLabel={storeLabels[store] || store}
          status={syncing ? 'running' : 'failed'}
          progress={syncProgress}
          note={syncNote}
          log={syncLog}
          startedAt={syncStartedAt}
          onRetry={runSync}
        />
      )}

      {/* Order card + grids only after the sync, so nothing pre-sync is shown. */}
      {!syncing && (<>
      <div className="poe-grid">
        <section className="poe-card">
          <header className="poe-card-head"><h3>Current order · {store || '—'}</h3></header>
          {!state ? <p className="poe-muted">Loading…</p> : order?.order_id ? (
            <dl className="poe-meta">
              <div><dt>Order</dt><dd>#{order.order_no ?? order.order_id} · {fmtStamp(state?.header?.order_datetime)}</dd></div>
              <div><dt>Last bill / GRN</dt><dd>{state?.header?.last_sale_bill_no || '—'} / {state?.header?.last_grn || '—'}</dd></div>
            </dl>
          ) : <p className="poe-muted">No order yet.</p>}
        </section>

        <section className="poe-card">
          <header className="poe-card-head"><h3>Submit</h3></header>
          <div className="poe-form">
            <label><span>Last bill</span>
              <div className="poe-readonly-field">{topBill || '—'}<span className="poe-auto-tag">(auto)</span></div>
            </label>
            <label><span>Last GRN</span>
              <div className="poe-readonly-field">{topGrn || '—'}<span className="poe-auto-tag">(auto)</span></div>
            </label>
          </div>
          {warning ? (
            <div className="status-line poe-warn">
              {warning}
              <button type="button" className="primary-button poe-inline-btn" disabled={busy} onClick={() => submit(true)}>Continue &amp; Process</button>
            </div>
          ) : (
            <button type="button" className="primary-button" disabled={!canSubmit} onClick={() => submit(false)}
              title={submitHint}>
              {simpleStatus === 'submitted' ? 'Submitted, please wait…' : 'Submit'}
            </button>
          )}
          {simpleStatus === 'submitted' && (
            <div className="poe-muted">Your order is being processed. This card will update automatically when it's done.</div>
          )}
        </section>
      </div>

      <RecentVerificationGrids session={session} store={store} syncing={syncing} reloadToken={reloadToken} onTopRow={(bill, grn) => { setTopBill(bill); setTopGrn(grn); }} />
      </>)}
    </section>
  );
}
