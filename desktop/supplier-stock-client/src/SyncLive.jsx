// Sync Live -- super admin. Same view as the HO web Sync Live page: every store's
// sync state grouped per tenant, current table/progress, last bill + last GRN,
// one-click full sync. Polls the HO every 3 s while visible.
import { Fragment, useCallback, useEffect, useMemo, useState } from 'react';
import { api } from './api/client.js';
import './syncLive.css';

const POLL_MS = 3000;

function asArray(value) {
  if (Array.isArray(value)) return value;
  if (Array.isArray(value?.items)) return value.items;
  if (Array.isArray(value?.data)) return value.data;
  return [];
}

// 09:29 for today, else 04/11 19:23; a date-only stamp (GRN) shows just 04/11.
function stamp(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const time = d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  const today = d.toDateString() === new Date().toDateString();
  const dateOnly = d.getHours() === 0 && d.getMinutes() === 0 && d.getSeconds() === 0;
  const day = today ? 'Today' : d.toLocaleDateString('en-GB', { day: '2-digit', month: '2-digit' });
  if (dateOnly) return day;
  return today ? time : `${day} ${time}`;
}

function storeStatus(row) {
  if (row.live || row.is_syncing) return 'Running';
  return String(row.agent_status || '').toLowerCase() === 'online' ? 'Online' : 'Offline';
}

function priority(row) {
  const st = storeStatus(row);
  return st === 'Running' ? 0 : st === 'Offline' ? 1 : 2;
}

function RefCell({ no, at }) {
  if (no == null || no === '') return <div className="sl-ref sl-dim">-</div>;
  const when = stamp(at);
  return (
    <div className="sl-ref" title={at ? `${no} · ${new Date(at).toLocaleString()}` : String(no)}>
      <span className="sl-refno">{no}</span>
      {when && <span className="sl-dim">{when}</span>}
    </div>
  );
}

const ACTIVITY = { COMPLETED: ['OK', 'ok'], FAILED: ['FLD', 'bad'], RUNNING: ['RUN', 'run'], PENDING: ['PND', 'wait'], QUEUED: ['Q', 'wait'] };

export default function SyncLive({ session, hidden }) {
  const [base, setBase] = useState(null);       // tenants + store->tenant map (loaded once)
  const [snap, setSnap] = useState(null);       // control center + live + history (polled)
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const [notice, setNotice] = useState('');

  useEffect(() => {
    let alive = true;
    Promise.all([api.listTenants(session), api.listAllStores(session)])
      .then(([tenants, stores]) => {
        if (!alive) return;
        const names = Object.fromEntries(asArray(tenants).map((t) => [String(t.tenant_id).toUpperCase(), t.tenant_name]));
        const tenantOf = Object.fromEntries(asArray(stores).map((s) => [String(s.store_id).toUpperCase(), String(s.tenant_id || '').toUpperCase()]));
        setBase({ names, tenantOf });
      })
      .catch((e) => alive && setError(e.message));
    return () => { alive = false; };
  }, [session]);

  const refresh = useCallback(async () => {
    const [cc, live, history] = await Promise.all([api.syncControlCenter(session), api.syncLive(session), api.syncHistory(session)]);
    setSnap({ cc, live: asArray(live), history: asArray(history) });
    setError('');
  }, [session]);

  useEffect(() => {
    if (hidden) return undefined;
    let alive = true;
    const tick = () => refresh().catch((e) => alive && setError(e.message));
    tick();
    const id = setInterval(tick, POLL_MS);
    return () => { alive = false; clearInterval(id); };
  }, [hidden, refresh]);

  const groups = useMemo(() => {
    if (!snap || !base) return [];
    const liveBy = Object.fromEntries(snap.live.map((l) => [String(l.store_id).toUpperCase(), l]));
    const rows = asArray(snap.cc?.stores).map((s) => {
      const key = String(s.store_id).toUpperCase();
      const tenantId = base.tenantOf[key] || '';
      return { ...s, tenant_id: tenantId, tenant_name: base.names[tenantId] || '-', live: liveBy[key] };
    });
    rows.sort((a, b) => a.tenant_name.localeCompare(b.tenant_name) || priority(a) - priority(b)
      || String(a.store_code || '').localeCompare(String(b.store_code || '')));
    const out = [];
    rows.forEach((r) => {
      const last = out[out.length - 1];
      if (last && last.name === r.tenant_name) last.stores.push(r);
      else out.push({ name: r.tenant_name, stores: [r] });
    });
    return out;
  }, [snap, base]);

  const allStores = groups.flatMap((g) => g.stores);

  async function queue(stores, key) {
    setBusy(key);
    setNotice('');
    try {
      const ready = stores.filter((s) => s.tenant_id);
      await Promise.all(ready.map((s) => api.createSyncTask({ tenant_id: s.tenant_id, store_id: s.store_id, execution_type: 'FULL', sync_mode: 'FULL' }, session)));
      setNotice(ready.length === 1 ? `Queued full sync for ${ready[0].store_code}.` : `Queued full sync for ${ready.length} stores.`);
      await refresh();
    } catch (e) {
      setNotice(`Sync failed: ${e.message}`);
    } finally {
      setBusy('');
    }
  }

  if (hidden) return null;
  const tenantName = (storeId) => (base ? base.names[base.tenantOf[String(storeId || '').toUpperCase()]] : null);

  return (
    <section className="sl-screen">
      <header className="screen-header">
        <div>
          <h2>Sync Live</h2>
          <p>Real-time view of every store's sync, grouped by tenant.</p>
        </div>
      </header>
      {error && <div className="sl-notice sl-notice-bad">{error}</div>}
      {notice && <div className="sl-notice">{notice}</div>}

      <div className="sl-card">
        <div className="sl-card-head">
          <strong>Live Store Grid</strong>
          <span className="sl-dim">{allStores.length} stores</span>
          <button type="button" className="sl-btn" disabled={busy !== '' || !allStores.length}
            onClick={() => queue(allStores, 'all')}>{busy === 'all' ? 'Queuing…' : '▶ Full Sync'}</button>
        </div>
        <div className="sl-grid">
          <div className="sl-row sl-head">
            <span>Store</span><span>Status</span><span>Current table</span><span>Progress</span>
            <span>Speed</span><span>Last sync</span><span>Last bill</span><span>Last GRN</span><span />
          </div>
          {!snap && !error && <div className="sl-empty">Loading…</div>}
          {groups.map((g) => (
            <Fragment key={g.name}>
              {groups.length > 1 && (
                <div className="sl-group">{g.name}<span>{g.stores.length} store{g.stores.length === 1 ? '' : 's'}</span></div>
              )}
              {g.stores.map((s) => {
                const st = storeStatus(s);
                return (
                  <div className="sl-row" key={s.store_id}>
                    <span className="sl-store"><b>{s.store_code}</b> <span className="sl-dim">{s.store_name}</span></span>
                    <span><span className={`sl-badge sl-badge-${st.toLowerCase()}`}>{st}</span></span>
                    <span className="sl-dim sl-ellipsis">{s.live?.current_table ?? s.current_activity ?? '-'}</span>
                    <span className="sl-progress">
                      {s.live ? (<><span className="sl-bar"><i style={{ width: `${Math.min(100, s.live.progress_pct || 0)}%` }} /></span>{s.live.progress_pct}%</>)
                        : <span className="sl-dim">Idle</span>}
                    </span>
                    <span>{s.live?.speed_rows_sec ? `${s.live.speed_rows_sec.toLocaleString()}/s` : '-'}</span>
                    <span className="sl-dim">{stamp(s.last_sync) || '-'}</span>
                    <RefCell no={s.last_bill_no} at={s.last_sale_bill_at} />
                    <RefCell no={s.last_grn_no} at={s.last_grn_at} />
                    <span>
                      <button type="button" className="sl-icon" title={`Sync ${s.store_code}`} disabled={busy !== '' || !s.tenant_id}
                        onClick={() => queue([s], s.store_id)}>{busy === s.store_id ? '…' : '▶'}</button>
                    </span>
                  </div>
                );
              })}
            </Fragment>
          ))}
        </div>
      </div>

      <div className="sl-card">
        <div className="sl-card-head"><strong>Recent Activity</strong><span className="sl-dim">Last 5 events</span></div>
        {(snap?.history || []).slice(0, 5).map((h) => {
          const [abbr, tone] = ACTIVITY[String(h.status || '').toUpperCase()] || [String(h.status || '---').slice(0, 3), 'wait'];
          const tenant = tenantName(h.store_id);
          return (
            <div className="sl-feed" key={h.sync_id || h.execution_id}>
              <span><b>{h.store_name || h.store_code || 'Store'}</b>{tenant && <span className="sl-dim"> · {tenant}</span>}</span>
              <span className={`sl-badge sl-badge-${tone}`}>{abbr}</span>
              <span className="sl-dim">{h.sync_mode === 'FULL' ? 'Full' : h.sync_mode || '-'}</span>
              <span className="sl-dim">{stamp(h.started_at)}</span>
            </div>
          );
        })}
        {snap && !snap.history.length && <div className="sl-empty">No activity yet.</div>}
      </div>
    </section>
  );
}
