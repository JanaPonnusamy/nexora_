// Live Queries / Repair -- platform-admin visibility into what's actually
// executing on central OrderNMC right now, with a Kill action. Built because
// store sync / order process / qty-check queries all run on independent
// threads per store (no global serialization), so several heavy, unbounded
// queries can land on the same SQL Server Express instance at once and
// deadlock or run away holding locks. This page is the "see it and kill it"
// tool, not a fix for the underlying query cost -- that's a separate change.
import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from './api/client.js';

const POLL_MS = 5000;

function fmtMs(ms) {
  if (ms == null) return '—';
  if (ms < 1000) return `${ms} ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)} s`;
  const m = Math.floor(s / 60);
  return `${m}m ${Math.round(s - m * 60)}s`;
}

export default function DbMonitorPage({ session }) {
  const [requests, setRequests] = useState([]);
  const [showAllSessions, setShowAllSessions] = useState(false);
  const [sessions, setSessions] = useState([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [killing, setKilling] = useState(null);
  const [note, setNote] = useState('');
  const [confirmKill, setConfirmKill] = useState(null);
  const [auto, setAuto] = useState(true);
  const mounted = useRef(true);

  useEffect(() => () => { mounted.current = false; }, []);

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    const calls = [api.dbMonitorRequests(session)];
    if (showAllSessions) calls.push(api.dbMonitorSessions(session));
    Promise.all(calls)
      .then(([reqs, sess]) => {
        if (!mounted.current) return;
        setRequests(reqs.requests || []);
        if (sess) setSessions(sess.sessions || []);
      })
      .catch((err) => { if (mounted.current) setError(err.message || 'Could not load live queries.'); })
      .finally(() => { if (mounted.current) setLoading(false); });
  }, [session, showAllSessions]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (!auto) return undefined;
    const t = setInterval(load, POLL_MS);
    return () => clearInterval(t);
  }, [auto, load]);

  const kill = async (sessionId) => {
    setKilling(sessionId);
    setError('');
    setNote('');
    try {
      await api.dbMonitorKill(sessionId, session);
      setNote(`Session ${sessionId} killed.`);
      setConfirmKill(null);
      await load();
    } catch (err) {
      setError(err.message || `Could not kill session ${sessionId}.`);
    } finally {
      setKilling(null);
    }
  };

  return (
    <section className="screen-panel poe-screen">
      <header className="screen-header">
        <div>
          <h2>Live Queries · Repair</h2>
          <p>What's running right now on central OrderNMC, longest-running first. Kill a stuck session to release its locks.</p>
        </div>
        <div className="poe-tools">
          <label className="poe-checkbox" style={{ gridColumn: 'auto' }}>
            <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} />
            Auto-refresh
          </label>
          <button type="button" className="secondary-button" onClick={load} disabled={loading}>
            {loading ? 'Loading…' : 'Refresh'}
          </button>
        </div>
      </header>

      {error && <div className="status-line error">{error}</div>}
      {note && <div className="status-line lgo-ok">{note}</div>}

      <section className="poe-card">
        <header className="poe-card-head">
          <h3>Active requests</h3>
          <span className="poe-muted">{requests.length} running</span>
        </header>
        <div className="trp-tablewrap poe-tablewrap">
          <table className="trp-table">
            <thead>
              <tr>
                <th>SPID</th><th>Elapsed</th><th>Status</th><th>Wait</th><th>Blocked by</th>
                <th>CPU</th><th>Reads</th><th>Rows</th>
                <th className="trp-left">Login / Host</th><th className="trp-left">Query</th><th />
              </tr>
            </thead>
            <tbody>
              {requests.map((r) => (
                <tr key={r.session_id} className={r.blocking_session_id ? 'lgo-warn' : ''}>
                  <td>{r.session_id}</td>
                  <td>{fmtMs(r.total_elapsed_ms)}</td>
                  <td>{r.status}</td>
                  <td>{r.wait_type || '—'}</td>
                  <td>{r.blocking_session_id || '—'}</td>
                  <td>{fmtMs(r.cpu_time_ms)}</td>
                  <td>{r.logical_reads != null ? r.logical_reads.toLocaleString() : '—'}</td>
                  <td>{r.row_count != null ? r.row_count.toLocaleString() : '—'}</td>
                  <td className="trp-left">{r.login_name} @ {r.host_name || '—'}<br /><span className="poe-muted">{r.program_name}</span></td>
                  <td className="trp-left poe-query-cell" title={r.query_text}>{r.query_text ? r.query_text.slice(0, 160) : '—'}</td>
                  <td>
                    {confirmKill === r.session_id ? (
                      <>
                        <button type="button" className="danger-button" disabled={killing === r.session_id}
                          onClick={() => kill(r.session_id)}>
                          {killing === r.session_id ? 'Killing…' : 'Confirm kill'}
                        </button>
                        <button type="button" className="secondary-button" onClick={() => setConfirmKill(null)}>Cancel</button>
                      </>
                    ) : (
                      <button type="button" className="danger-button" onClick={() => setConfirmKill(r.session_id)}>Kill</button>
                    )}
                  </td>
                </tr>
              ))}
              {!loading && !requests.length && (
                <tr><td colSpan={11} className="poe-muted">Nothing is actively running right now.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="poe-card">
        <header className="poe-card-head">
          <h3>All sessions</h3>
          <div className="poe-tools">
            <label className="poe-checkbox" style={{ gridColumn: 'auto' }}>
              <input type="checkbox" checked={showAllSessions} onChange={(e) => setShowAllSessions(e.target.checked)} />
              Show (includes idle connections)
            </label>
          </div>
        </header>
        {showAllSessions && (
          <div className="trp-tablewrap poe-tablewrap">
            <table className="trp-table">
              <thead>
                <tr>
                  <th>SPID</th><th>Status</th><th>Last request</th><th>Elapsed</th><th>Blocked by</th>
                  <th className="trp-left">Login / Host / Program</th>
                </tr>
              </thead>
              <tbody>
                {sessions.map((s) => (
                  <tr key={s.session_id}>
                    <td>{s.session_id}</td>
                    <td>{s.status}</td>
                    <td>{s.last_request_start_time ? new Date(s.last_request_start_time).toLocaleTimeString() : '—'}</td>
                    <td>{fmtMs(s.total_elapsed_ms)}</td>
                    <td>{s.blocking_session_id || '—'}</td>
                    <td className="trp-left">{s.login_name} @ {s.host_name || '—'} · {s.program_name}</td>
                  </tr>
                ))}
                {!sessions.length && <tr><td colSpan={6} className="poe-muted">No sessions.</td></tr>}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </section>
  );
}
