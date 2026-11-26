// Morning auto order settings + today's progress, one card per legacy
// database (tenant) the HO serves -- backend/modules/legacy_order/
// morning_order.py. Each chosen store gets ONE order a day: once its agent
// heartbeat is live, sync -> a bill from today must be in SaleInformation ->
// Order Process -> push the warehouse (SHP / NMW) stock. Identical copy in
// desktop/nextech-mediq/src/modules/legacy-order/morningOrder.jsx; the host
// passes the three API calls.
import { useCallback, useEffect, useRef, useState } from 'react';

// datetime.weekday() numbers, as the backend stores them.
const DAYS = [['Mon', 0], ['Tue', 1], ['Wed', 2], ['Thu', 3], ['Fri', 4], ['Sat', 5], ['Sun', 6]];
const DEFAULT_DAYS = [0, 1, 2, 3, 4, 5];

const STATUS_LABEL = {
  WAITING: 'Waiting', RUNNING: 'Running', DONE: 'Done', MANUAL: 'Manual today', FAILED: 'Failed',
};

function fmtTime(value) {
  if (!value) return '—';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
}

function TenantCard({ sch, running, onSave, onRetry }) {
  const [draft, setDraft] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [note, setNote] = useState('');
  const available = sch.available_stores || [];
  const view = draft || {
    enabled: Boolean(sch.enabled), run_at: sch.run_at || '07:45', until: sch.until || '09:00',
    retry_minutes: sch.retry_minutes || 10,
    // Ordered: the list order is the run order (first store runs first).
    stores: (sch.stores || available).map((s) => s.toUpperCase()),
    days: new Set(sch.days || DEFAULT_DAYS),
  };
  const edit = (patch) => { setNote(''); setDraft({ ...view, ...patch }); };
  const ticked = (name) => view.stores.includes(name.toUpperCase());
  const toggle = (name) => {
    const key = name.toUpperCase();
    edit({ stores: ticked(name) ? view.stores.filter((s) => s !== key) : [...view.stores, key] });
  };
  const move = (index, delta) => {
    const next = [...view.stores];
    const to = index + delta;
    if (to < 0 || to >= next.length) return;
    [next[index], next[to]] = [next[to], next[index]];
    edit({ stores: next });
  };
  const toggleDay = (d) => {
    const next = new Set(view.days);
    if (next.has(d)) next.delete(d); else next.add(d);
    edit({ days: next });
  };
  const all = available.length > 0 && available.every((s) => ticked(s));
  const nameOf = (key) => available.find((s) => s.toUpperCase() === key) || key;

  const save = async () => {
    setBusy(true);
    setError('');
    try {
      await onSave(sch.tenant_key, {
        enabled: view.enabled, run_at: view.run_at, until: view.until, retry_minutes: Number(view.retry_minutes) || 10,
        stores: view.stores.map(nameOf),
        days: [...view.days].sort(),
      });
      setDraft(null);
      setNote('Saved.');
    } catch (err) {
      setError(err.message || 'Could not save.');
    } finally {
      setBusy(false);
    }
  };

  if (sch.error) {
    return (
      <section className="mao-card">
        <header className="mao-head"><h4>{sch.tenant_name || 'Default'} <small>{sch.database}</small></h4></header>
        <div className="status-line error">{sch.error}</div>
      </section>
    );
  }
  return (
    <section className={`mao-card${view.enabled ? ' is-on' : ''}`}>
      <header className="mao-head">
        <h4>{sch.tenant_name || 'Default tenant'} <small>{sch.database}</small></h4>
        <label className="mao-switch">
          <input type="checkbox" checked={view.enabled} onChange={(e) => edit({ enabled: e.target.checked })} />
          Run the morning order automatically
        </label>
      </header>
      <div className="mao-row">
        <label>From <input type="time" value={view.run_at} onChange={(e) => edit({ run_at: e.target.value })} /></label>
        <label>Last start <input type="time" value={view.until} onChange={(e) => edit({ until: e.target.value })} /></label>
        <label>Retry every
          <input type="number" min={2} max={120} className="mao-num" value={view.retry_minutes}
                 onChange={(e) => edit({ retry_minutes: e.target.value })} /> min
        </label>
        <button type="button" className="primary-button" disabled={busy || !draft} onClick={save}>{busy ? 'Saving…' : 'Save'}</button>
        {note && <span className="mao-note">{note}</span>}
      </div>
      <div className="mao-stores">
        <label className="mao-chip mao-chip--all">
          <input type="checkbox" checked={all}
                 onChange={(e) => edit({ stores: e.target.checked ? [...view.stores, ...available.map((s) => s.toUpperCase()).filter((s) => !view.stores.includes(s))] : [] })} />
          All stores
        </label>
        {view.stores.map((key, i) => (
          <span key={key} className="mao-chip mao-chip--on" title="Run order: the first store runs first">
            <b className="mao-order">{i + 1}</b>
            <label><input type="checkbox" checked onChange={() => toggle(key)} /> {nameOf(key)}</label>
            <button type="button" className="mao-move" disabled={i === 0} aria-label={`Run ${nameOf(key)} earlier`} onClick={() => move(i, -1)}>◀</button>
            <button type="button" className="mao-move" disabled={i === view.stores.length - 1} aria-label={`Run ${nameOf(key)} later`} onClick={() => move(i, 1)}>▶</button>
          </span>
        ))}
        {available.filter((s) => !ticked(s)).map((s) => (
          <label key={s} className="mao-chip">
            <input type="checkbox" checked={false} onChange={() => toggle(s)} /> {s}
          </label>
        ))}
      </div>
      <div className="mao-stores">
        {DAYS.map(([label, d]) => (
          <label key={d} className="mao-chip">
            <input type="checkbox" checked={view.days.has(d)} onChange={() => toggleDay(d)} /> {label}
          </label>
        ))}
      </div>
      {error && <div className="status-line error">{error}</div>}
      <p className="mao-hint">
        On the ticked days each ticked store gets one order, one store at a time in the numbered order: when its agent
        comes online (heartbeat) it syncs, waits until a sale bill from today is in SaleInformation, generates the order
        (saved engine, source and compare mode), then pushes the warehouse stock. Offline or no bill yet = tried again
        every {view.retry_minutes} min until {view.until}. Auto-repair: from 30 min before {view.run_at} an outdated
        Store Agent is updated; a failed sync restarts the agent, or updates / reinstalls it when it stopped beating.
        A store already run by hand today is left alone; the warehouse is never run.
      </p>
      <table className="trp-table mao-table">
        <thead>
          <tr>
            <th className="trp-left">Store</th><th className="trp-left">Today</th><th>Tries</th><th>Last try</th>
            <th>Next try</th><th>Done</th><th className="trp-left">Detail</th><th />
          </tr>
        </thead>
        <tbody>
          {(sch.today || []).map((r) => {
            const live = running && running.store_name === r.store_name && running.tenant === sch.tenant_key;
            const status = live ? 'RUNNING' : r.status;
            return (
              <tr key={r.store_name}>
                <td className="trp-left"><b>{r.store_name}</b></td>
                <td className="trp-left"><span className={`mao-badge mao-badge--${String(status).toLowerCase()}`}>{STATUS_LABEL[status] || status}</span></td>
                <td>{r.attempts || 0}</td>
                <td>{fmtTime(r.last_attempt_at)}</td>
                <td>{fmtTime(r.next_attempt_at)}</td>
                <td>{fmtTime(r.finished_at)}</td>
                <td className="trp-left mao-detail" title={live ? running.step : r.message || ''}>{live ? running.step : r.message || '—'}</td>
                <td>
                  {['DONE', 'FAILED', 'MANUAL'].includes(status) && (
                    <button type="button" className="secondary-button poe-inline-btn" title="Clear today's result so it runs again once the store is online"
                            onClick={() => onRetry(sch.tenant_key, r.store_name)}>Run again</button>
                  )}
                </td>
              </tr>
            );
          })}
          {!(sch.today || []).length && <tr><td colSpan={8} className="poe-muted">No store selected.</td></tr>}
        </tbody>
      </table>
    </section>
  );
}

export default function MorningOrderDialog({ load, save, retry, onClose }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const dialogRef = useRef(null);

  const refresh = useCallback(() => load().then((d) => { setData(d); setError(''); }).catch((err) => setError(err.message || 'Could not load.')), [load]);
  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 10000);
    return () => clearInterval(t);
  }, [refresh]);
  useEffect(() => {
    dialogRef.current?.focus();
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const onSave = async (key, payload) => { await save(key, payload); await refresh(); };
  const onRetry = async (key, store) => {
    try { await retry(key, store); await refresh(); } catch (err) { setError(err.message || 'Could not reset.'); }
  };

  return (
    <div className="lgo-modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="lgo-modal" role="dialog" aria-modal="true" aria-labelledby="mao-title" tabIndex={-1} ref={dialogRef}>
        <header className="lgo-modal-head">
          <h3 id="mao-title">🌅 Morning auto order</h3>
          <button type="button" className="lgo-modal-x" aria-label="Close" onClick={onClose}>×</button>
        </header>
        <div className="mao-body">
          {error && <div className="status-line error">{error}</div>}
          {!data ? <p className="poe-muted">Loading…</p> : data.schedules.map((sch) => (
            <TenantCard key={sch.tenant_key} sch={sch} running={data.running} onSave={onSave} onRetry={onRetry} />
          ))}
        </div>
      </div>
    </div>
  );
}
