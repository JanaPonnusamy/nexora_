// Legacy Order -- super-admin Order Process across every tenant.
// OrderNMC is ONE central database that holds every tenant's branches
// (OrderNMC.Stores.StoreName = the platform store_code), so this screen groups
// its stores by platform tenant, lets the operator tick stores from any tenant
// and runs /api/legacy-order/order-process for them as a queue. Jobs run on
// the HO backend (in memory); the screen only starts them and polls their
// progress, so it is kept mounted (App.jsx) and re-attaches to running jobs
// from GET /jobs when it loads.
//
// Warnings follow the owner's single-warning rule (order-process-single-
// warning): a stale-order OR pending-assignment 409 parks that store as
// "warning"; Continue & Process re-sends with confirmed_stale_order, which
// acknowledges both gates server-side.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from './api/client.js';

const POLL_MS = 1500;
const LOST_AFTER_MS = 120000;
const UNMAPPED = '__unmapped__';
const ENGINE_LABEL = { LEGACY: 'Legacy', RULEBOOK: 'Rule book' };
const BUSY = new Set(['queued', 'starting', 'running']);

const sleep = (ms) => new Promise((resolve) => { setTimeout(resolve, ms); });
const codeKey = (value) => String(value || '').trim().toUpperCase();
const asArray = (value) => (Array.isArray(value) ? value : []);

function positiveInt(value) {
  const n = parseInt(value, 10);
  return Number.isFinite(n) && n > 0 ? n : null;
}

function fmtStamp(value) {
  if (!value) return '';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleString('en-GB', {
    day: '2-digit', month: '2-digit', hour: 'numeric', minute: '2-digit', hour12: true,
  }).replace(/\b([ap])m\b/gi, (s) => s.toUpperCase());
}

function isToday(value) {
  if (!value) return false;
  const d = new Date(value);
  return !Number.isNaN(d.getTime()) && d.toDateString() === new Date().toDateString();
}

function StatusCell({ entry }) {
  const job = entry?.job;
  switch (entry?.state) {
    case 'queued':
      return <span className="lgo-status lgo-muted">Queued</span>;
    case 'starting':
      return <span className="lgo-status lgo-run">Starting…</span>;
    case 'running':
      return (
        <span className="lgo-status lgo-run">
          <progress max={job?.total_steps || 1} value={job?.step || 0} />
          <span className="lgo-msg" title={job?.message || ''}>
            {job && job.kind !== 'order' ? `${job.kind}: ` : ''}{job?.message || 'Running…'}
          </span>
        </span>
      );
    case 'completed':
      return (
        <span className="lgo-status lgo-ok" title={job?.warning || ''}>
          ✓ {job?.kind === 'order' && job?.result?.rows != null ? `${job.result.rows} rows` : `${job?.kind || 'job'} done`}
          <span className="lgo-muted"> · {fmtStamp(job?.finished_at)}</span>
          {job?.warning && <span className="lgo-warn-dot" aria-label="Completed with a warning"> ⚠</span>}
        </span>
      );
    case 'warning':
      return <span className="lgo-status lgo-warn" title={entry.message}>⚠ {entry.message}</span>;
    case 'failed':
    case 'error': {
      const text = entry.message || job?.error || 'Failed';
      return <span className="lgo-status lgo-bad" title={text}>✗ {text}</span>;
    }
    default:
      return <span className="lgo-muted">—</span>;
  }
}

export default function LegacyOrderGeneration({ session, hidden }) {
  const [tenants, setTenants] = useState([]);
  const [tenantOf, setTenantOf] = useState({});
  const [stores, setStores] = useState([]);
  const [defaults, setDefaults] = useState(null);
  const [engines, setEngines] = useState({});
  const [headers, setHeaders] = useState({});
  const [cfg, setCfg] = useState({});
  const [run, setRun] = useState({});
  const [selected, setSelected] = useState(() => new Set());
  const [tenantFilter, setTenantFilter] = useState('all');
  const [parallel, setParallel] = useState(1);
  const [ackWarnings, setAckWarnings] = useState(false);
  const [logStore, setLogStore] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [queued, setQueued] = useState(0);

  const alive = useRef(true);
  const sessionRef = useRef(session);
  sessionRef.current = session;
  const cfgRef = useRef(cfg);
  cfgRef.current = cfg;
  const runRef = useRef(run);
  runRef.current = run;
  const parallelRef = useRef(parallel);
  parallelRef.current = parallel;
  const queueRef = useRef([]);
  const activeRef = useRef(0);
  const watching = useRef(new Set());

  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; queueRef.current = []; };
  }, []);

  const patchRun = useCallback((name, patch) => {
    setRun((cur) => ({ ...cur, [name]: { ...cur[name], ...patch } }));
  }, []);

  const loadHeader = useCallback((name) => {
    api.legacyOrderHeader(name, sessionRef.current)
      .then((h) => { if (alive.current) setHeaders((cur) => ({ ...cur, [name]: h })); })
      .catch(() => {});
  }, []);

  // Polls one job until it leaves 'running'. A 404 means the backend restarted
  // and the in-memory job is gone; other errors keep polling for a while.
  const watch = useCallback(async (jobId, name) => {
    if (watching.current.has(jobId)) return null;
    watching.current.add(jobId);
    let lastOk = Date.now();
    try {
      while (alive.current) {
        try {
          const job = await api.legacyJob(jobId, sessionRef.current);
          lastOk = Date.now();
          if (!alive.current) return null;
          patchRun(name, { state: job.status, job, message: '' });
          if (job.status !== 'running') {
            loadHeader(name);
            return job;
          }
        } catch (err) {
          if (/job not found/i.test(err.message)) {
            patchRun(name, { state: 'failed', message: 'The server restarted while this ran, so the task was lost. Run it again.' });
            return null;
          }
          if (Date.now() - lastOk > LOST_AFTER_MS) {
            patchRun(name, { state: 'failed', message: `Lost contact with the server: ${err.message}` });
            return null;
          }
        }
        await sleep(POLL_MS);
      }
      return null;
    } finally {
      watching.current.delete(jobId);
    }
  }, [patchRun, loadHeader]);

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const s = sessionRef.current;
      const [tenantRows, platformStores, legacyRows, dflt, jobs] = await Promise.all([
        api.listTenants(s).catch(() => []),
        api.listAllStores(s).catch(() => []),
        api.legacyStores(s, true),
        api.legacyDefaults(s).catch(() => null),
        api.legacyJobs(s).catch(() => []),
      ]);
      if (!alive.current) return;
      const storeList = asArray(legacyRows);
      setTenants(asArray(tenantRows));
      setTenantOf(Object.fromEntries(asArray(platformStores).map((p) => [codeKey(p.store_code), String(p.tenant_id || '')])));
      setStores(storeList);
      setDefaults(dflt);
      const names = storeList.map((st) => st.store_name);
      names.forEach(loadHeader);
      Promise.all(names.map((n) => api.legacyStoreEngine(n, s)
        .then((r) => [n, r.engine])
        .catch(() => [n, 'LEGACY'])))
        .then((pairs) => { if (alive.current) setEngines(Object.fromEntries(pairs)); });
      // /jobs is newest first: the first job per store is its latest. Running
      // ones (started here earlier, from the web console or another PC) are
      // re-attached so their progress shows.
      const latest = {};
      asArray(jobs).forEach((job) => { if (!latest[job.store_name]) latest[job.store_name] = job; });
      setRun((cur) => {
        const next = { ...cur };
        Object.entries(latest).forEach(([name, job]) => {
          if (!BUSY.has(next[name]?.state)) next[name] = { state: job.status, job, message: '' };
        });
        return next;
      });
      Object.entries(latest).forEach(([name, job]) => {
        if (job.status === 'running') watch(job.job_id, name);
      });
    } catch (err) {
      if (alive.current) setError(err.message || 'Could not load the OrderNMC stores.');
    } finally {
      if (alive.current) setLoading(false);
    }
  }, [loadHeader, watch]);

  useEffect(() => { load(); }, [load]);

  const startOne = useCallback(async (name, acknowledge) => {
    const c = cfgRef.current[name] || {};
    patchRun(name, { state: 'starting', message: '', job: null });
    try {
      const { job_id: jobId } = await api.legacyStartOrderProcess({
        store_name: name,
        // null = the store's saved engine / the server's store-or-warehouse
        // default (sending 13/18 to a warehouse would bypass its 32/35 profile).
        engine: c.engine || null,
        min_days: positiveInt(c.minDays),
        max_days: positiveInt(c.maxDays),
        recency_days: positiveInt(c.recencyDays),
        mode: 'local',
        confirmed_stale_order: Boolean(acknowledge),
      }, sessionRef.current);
      patchRun(name, { state: 'running' });
      return await watch(jobId, name);
    } catch (err) {
      const message = err.message || 'Could not start Order Process.';
      const warning = /confirm order & process/i.test(message) && !/already running/i.test(message);
      patchRun(name, { state: warning ? 'warning' : 'error', message });
      return null;
    }
  }, [patchRun, watch]);

  const pump = useCallback(() => {
    while (alive.current && activeRef.current < parallelRef.current && queueRef.current.length) {
      const { name, acknowledge } = queueRef.current.shift();
      activeRef.current += 1;
      startOne(name, acknowledge).finally(() => {
        activeRef.current -= 1;
        if (alive.current) pump();
      });
    }
    setQueued(queueRef.current.length);
  }, [startOne]);

  const enqueue = useCallback((names, acknowledge) => {
    const fresh = names.filter((n) => !BUSY.has(runRef.current[n]?.state) && !queueRef.current.some((q) => q.name === n));
    if (!fresh.length) return;
    queueRef.current.push(...fresh.map((name) => ({ name, acknowledge })));
    fresh.forEach((n) => patchRun(n, { state: 'queued', message: '' }));
    pump();
  }, [patchRun, pump]);

  // A raised limit takes effect immediately; a lowered one as jobs finish.
  useEffect(() => { pump(); }, [parallel, pump]);

  const stopQueue = () => {
    queueRef.current.forEach((q) => patchRun(q.name, { state: '', message: '' }));
    queueRef.current = [];
    setQueued(0);
  };

  const groups = useMemo(() => {
    const byTenant = new Map();
    stores.forEach((st) => {
      const tid = tenantOf[codeKey(st.store_name)] || UNMAPPED;
      if (!byTenant.has(tid)) byTenant.set(tid, []);
      byTenant.get(tid).push(st);
    });
    const nameOf = (tid) => (tid === UNMAPPED
      ? 'Not in platform'
      : String(tenants.find((t) => String(t.tenant_id) === tid)?.tenant_name || 'Unknown tenant').trim());
    return [...byTenant.entries()]
      .map(([tid, list]) => ({ tid, name: nameOf(tid), stores: list }))
      .sort((a, b) => (a.tid === UNMAPPED) - (b.tid === UNMAPPED) || a.name.localeCompare(b.name));
  }, [stores, tenantOf, tenants]);

  const visibleGroups = tenantFilter === 'all' ? groups : groups.filter((g) => g.tid === tenantFilter);
  const visibleNames = visibleGroups.flatMap((g) => g.stores.map((st) => st.store_name));
  const toRun = visibleNames.filter((n) => selected.has(n) && !BUSY.has(run[n]?.state));
  const warned = visibleNames.filter((n) => run[n]?.state === 'warning');
  const counts = useMemo(() => {
    const c = { running: 0, queued: 0, completed: 0, warning: 0, failed: 0 };
    Object.values(run).forEach((r) => {
      if (r?.state === 'running' || r?.state === 'starting') c.running += 1;
      else if (r?.state === 'error' || r?.state === 'failed') c.failed += 1;
      else if (r?.state in c) c[r.state] += 1;
    });
    return c;
  }, [run]);

  const warehouses = new Set(asArray(defaults?.warehouse_stores).map(codeKey));
  const isWarehouse = (name) => warehouses.has(codeKey(name));
  const recencyDefault = (name) => (isWarehouse(name)
    ? (defaults?.warehouse_recency_days ?? 90)
    : (defaults?.recency_days ?? 15));

  const toggle = (names, on) => setSelected((cur) => {
    const next = new Set(cur);
    names.forEach((n) => (on ? next.add(n) : next.delete(n)));
    return next;
  });
  const patchCfg = (name, patch) => setCfg((cur) => ({ ...cur, [name]: { ...cur[name], ...patch } }));

  const generate = (names) => {
    if (!names.length) return;
    const list = names.join(', ');
    // eslint-disable-next-line no-alert
    if (!window.confirm(`Generate a new order for ${names.length} store${names.length > 1 ? 's' : ''}?\n\n${list}\n\nEach store runs Order Process (sync + order) on the HO backend.${ackWarnings ? '\nWarnings (stale order / pending assignment) are acknowledged for this batch.' : ''}`)) return;
    setError('');
    enqueue(names, ackWarnings);
  };

  const logEntry = logStore ? run[logStore] : null;
  const logLines = asArray(logEntry?.job?.log);

  return (
    <section className={`screen-panel lgo-screen${hidden ? ' lgo-hidden' : ''}`} aria-hidden={hidden || undefined}>
      <header className="screen-header lgo-header">
        <div>
          <h2>Legacy Order</h2>
          <p>Generate OrderNMC orders for stores in every tenant. Super admin only.</p>
        </div>
        <div className="lgo-counts" aria-live="polite">
          <span className="lgo-count lgo-run">Running {counts.running}</span>
          <span className="lgo-count">Queued {queued}</span>
          <span className="lgo-count lgo-ok">Done {counts.completed}</span>
          <span className="lgo-count lgo-warn">Warnings {counts.warning}</span>
          <span className="lgo-count lgo-bad">Failed {counts.failed}</span>
        </div>
      </header>

      <div className="trp-bar lgo-bar">
        <div className="rta-chips" role="tablist" aria-label="Tenant">
          <button type="button" role="tab" aria-selected={tenantFilter === 'all'} className={`rta-chip${tenantFilter === 'all' ? ' active' : ''}`} onClick={() => setTenantFilter('all')}>
            All tenants<span className="rta-count">{stores.length}</span>
          </button>
          {groups.map((g) => (
            <button key={g.tid} type="button" role="tab" aria-selected={tenantFilter === g.tid} className={`rta-chip${tenantFilter === g.tid ? ' active' : ''}`} onClick={() => setTenantFilter(g.tid)}>
              {g.name}<span className="rta-count">{g.stores.length}</span>
            </button>
          ))}
        </div>
        <div className="trp-actions">
          <label className="lgo-inline">
            Run
            <select value={parallel} onChange={(e) => setParallel(Number(e.target.value))}>
              <option value={1}>1 at a time</option>
              <option value={2}>2 at a time</option>
              <option value={3}>3 at a time</option>
            </select>
          </label>
          <label className="lgo-inline lgo-ack" title="Send the batch with the stale-order / pending-assignment warning already confirmed">
            <input type="checkbox" checked={ackWarnings} onChange={(e) => setAckWarnings(e.target.checked)} />
            Confirm warnings
          </label>
          {queued > 0 && <button type="button" className="secondary-button" onClick={stopQueue}>Stop queue ({queued})</button>}
          {warned.length > 0 && (
            <button type="button" className="secondary-button" onClick={() => enqueue(warned, true)}>Continue warned ({warned.length})</button>
          )}
          <button type="button" className="secondary-button" onClick={load} disabled={loading}>{loading ? 'Loading…' : 'Refresh'}</button>
          <button type="button" className="primary-button" disabled={!toRun.length} onClick={() => generate(toRun)}>
            Generate selected ({toRun.length})
          </button>
        </div>
      </div>

      {error && <div className="status-line error">{error}</div>}

      <div className="trp-tablewrap lgo-tablewrap">
        <table className="trp-table lgo-table">
          <thead>
            <tr>
              <th className="lgo-check-col" aria-label="Select" />
              <th className="trp-left">Store</th>
              <th className="trp-left">Type</th>
              <th className="trp-left">Engine</th>
              <th title="Min days of cover (blank = store/warehouse default)">Min</th>
              <th title="Max days of cover (blank = store/warehouse default)">Max</th>
              <th title="Only products sold in the last N days are ordered">Recency</th>
              <th className="trp-left">Current order</th>
              <th className="trp-left">Last bill</th>
              <th className="trp-left lgo-status-col">Status</th>
              <th aria-label="Action" />
            </tr>
          </thead>
          <tbody>
            {visibleGroups.map((g) => {
              const names = g.stores.map((st) => st.store_name);
              const idle = names.filter((n) => !BUSY.has(run[n]?.state));
              const allOn = idle.length > 0 && idle.every((n) => selected.has(n));
              return [
                <tr key={`g-${g.tid}`} className="lgo-group">
                  <td className="lgo-check-col">
                    <input type="checkbox" aria-label={`Select every store in ${g.name}`} checked={allOn} disabled={!idle.length} onChange={(e) => toggle(idle, e.target.checked)} />
                  </td>
                  <td colSpan={10} className="trp-left">
                    {g.name} <span className="lgo-muted">· {g.stores.length} store{g.stores.length > 1 ? 's' : ''}</span>
                  </td>
                </tr>,
                ...g.stores.map((st) => {
                  const name = st.store_name;
                  const entry = run[name];
                  const busy = BUSY.has(entry?.state);
                  const c = cfg[name] || {};
                  const head = headers[name];
                  const agent = !st.server_name && !st.database;
                  const warehouse = isWarehouse(name);
                  return (
                    <tr key={name} className={`lgo-row${logStore === name ? ' lgo-selected' : ''}`} onClick={() => setLogStore(name)}>
                      <td className="lgo-check-col" onClick={(e) => e.stopPropagation()}>
                        <input type="checkbox" aria-label={`Select ${name}`} checked={selected.has(name)} disabled={busy} onChange={(e) => toggle([name], e.target.checked)} />
                      </td>
                      <td className="trp-left lgo-store"><strong>{name}</strong></td>
                      <td className="trp-left">
                        {warehouse ? <span className="lgo-tag lgo-tag-wh">Warehouse</span> : agent ? <span className="lgo-tag lgo-tag-agent">Agent</span> : <span className="lgo-tag">LAN</span>}
                      </td>
                      <td className="trp-left" onClick={(e) => e.stopPropagation()}>
                        <select aria-label={`${name} engine`} value={c.engine || ''} disabled={busy} onChange={(e) => patchCfg(name, { engine: e.target.value })}>
                          <option value="">{`Saved · ${ENGINE_LABEL[engines[name]] || '…'}`}</option>
                          <option value="LEGACY">Legacy</option>
                          <option value="RULEBOOK">Rule book</option>
                        </select>
                      </td>
                      {['minDays', 'maxDays', 'recencyDays'].map((field) => (
                        <td key={field} onClick={(e) => e.stopPropagation()}>
                          <input
                            className="lgo-num"
                            inputMode="numeric"
                            aria-label={`${name} ${field}`}
                            value={c[field] ?? ''}
                            disabled={busy}
                            placeholder={field === 'recencyDays' ? String(recencyDefault(name)) : (warehouse ? 'auto' : String(field === 'minDays' ? defaults?.min_days ?? 13 : defaults?.max_days ?? 18))}
                            onChange={(e) => patchCfg(name, { [field]: e.target.value.replace(/\D/g, '') })}
                          />
                        </td>
                      ))}
                      <td className="trp-left">
                        {head?.order_id != null ? (
                          <span>
                            #{head.order_no ?? head.order_id}
                            <span className="lgo-muted"> · {fmtStamp(head.order_datetime)}</span>
                            {isToday(head.order_datetime) && <span className="lgo-tag lgo-tag-today">today</span>}
                          </span>
                        ) : <span className="lgo-muted">—</span>}
                      </td>
                      <td className="trp-left lgo-muted">{fmtStamp(head?.last_bill_datetime) || '—'}</td>
                      <td className="trp-left lgo-status-col"><StatusCell entry={entry} /></td>
                      <td onClick={(e) => e.stopPropagation()}>
                        {entry?.state === 'warning' ? (
                          <button type="button" className="secondary-button lgo-btn" onClick={() => enqueue([name], true)}>Continue &amp; Process</button>
                        ) : (
                          <button type="button" className="secondary-button lgo-btn" disabled={busy} onClick={() => generate([name])}>Generate</button>
                        )}
                      </td>
                    </tr>
                  );
                }),
              ];
            })}
            {!loading && !visibleGroups.length && (
              <tr><td colSpan={11} className="lgo-muted">No active OrderNMC stores.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="lgo-log">
        <div className="lgo-log-head">
          {logStore ? <>Task log · <strong>{logStore}</strong>{logEntry?.job?.kind ? <span className="lgo-muted"> · {logEntry.job.kind}</span> : null}</> : 'Task log · click a store'}
        </div>
        <div className="lgo-log-body">
          {logLines.length
            ? logLines.slice(-60).map((line, i) => (
              <div key={i} className="lgo-log-line"><span className="lgo-muted">{fmtStamp(line.at)}</span> {line.message}</div>
            ))
            : <div className="lgo-muted">{logStore ? (logEntry?.message || 'No task run yet for this store.') : ''}</div>}
          {logEntry?.job?.error && <div className="lgo-log-line lgo-bad">{logEntry.job.error}</div>}
          {logEntry?.job?.warning && <div className="lgo-log-line lgo-warn">{logEntry.job.warning}</div>}
        </div>
      </div>
    </section>
  );
}
