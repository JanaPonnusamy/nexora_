// "Under maintenance" screen: polls the HO's unauthenticated
// GET /health/maintenance (backend/modules/legacy_order/db_guard.py) and
// covers the app while the HO cannot be reached or its database is down /
// being auto-repaired, with the reason. Hides itself once the HO answers
// healthy again. Identical copy of
// desktop/supplier-stock-client/src/MaintenanceScreen.jsx; the host passes
// getBaseUrl (read on every poll, so a Settings change / HO failover is used).
import { useCallback, useEffect, useRef, useState } from 'react';
import './maintenance.css';

const POLL_MS = 15000;
const DOWN_POLL_MS = 5000;
const TIMEOUT_MS = 8000;
// One dropped poll is a blip; two in a row is an outage.
const FAILS_BEFORE_SHOWING = 2;

async function probe(baseUrl) {
  const base = String(baseUrl || '').replace(/\/+$/, '');
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(`${base}/health/maintenance`, { signal: controller.signal, cache: 'no-store' });
    if (res.status === 404) {
      // An HO older than the DB guard: reachable is all we can tell.
      const health = await fetch(`${base}/health`, { signal: controller.signal, cache: 'no-store' });
      return health.ok ? { maintenance: false } : { unreachable: true, detail: `HO answered ${health.status}` };
    }
    if (!res.ok) return { unreachable: true, detail: `HO answered ${res.status}` };
    return await res.json();
  } catch (err) {
    return { unreachable: true, detail: err?.name === 'AbortError' ? 'no answer in 8s' : (err?.message || 'network error') };
  } finally {
    clearTimeout(timer);
  }
}

export default function MaintenanceScreen({ getBaseUrl }) {
  const [state, setState] = useState(null); // null = healthy / not known yet
  const [checkedAt, setCheckedAt] = useState(null);
  // "Hide for 2 min": lets the operator reach Settings (e.g. another HO link).
  const [hiddenUntil, setHiddenUntil] = useState(0);
  const fails = useRef(0);
  const timer = useRef(null);

  const check = useCallback(async () => {
    clearTimeout(timer.current);
    const baseUrl = getBaseUrl();
    const r = await probe(baseUrl);
    setCheckedAt(new Date());
    let next = null;
    if (r.unreachable) {
      fails.current += 1;
      if (fails.current >= FAILS_BEFORE_SHOWING) {
        next = { kind: 'ho', title: 'HO under maintenance', message: 'Working on connecting to the HO server…', detail: `${baseUrl} — ${r.detail}` };
      }
    } else {
      fails.current = 0;
      if (r.maintenance) {
        next = { kind: 'db', title: 'Database under maintenance', message: r.message || 'Working on connecting to the database…',
                 detail: (r.databases || []).filter((d) => !d.ok).map((d) => `${d.name}: ${d.state || 'unreachable'}`).join(' · ') };
      }
    }
    setState(next);
    timer.current = setTimeout(check, next || fails.current ? DOWN_POLL_MS : POLL_MS);
  }, [getBaseUrl]);

  useEffect(() => {
    check();
    return () => clearTimeout(timer.current);
  }, [check]);

  if (!state || (checkedAt && checkedAt.getTime() < hiddenUntil)) return null;
  return (
    <div className="mnt-backdrop" role="alertdialog" aria-modal="true" aria-labelledby="mnt-title" aria-describedby="mnt-msg">
      <div className="mnt-card">
        <div className="mnt-spinner" aria-hidden="true" />
        <h2 id="mnt-title">{state.title}</h2>
        <p id="mnt-msg" className="mnt-msg">{state.message}</p>
        {state.detail && <p className="mnt-detail">{state.detail}</p>}
        <p className="mnt-foot">
          Automatic repair is running. This screen closes by itself when the connection is back.
          {checkedAt && <> Last check {checkedAt.toLocaleTimeString('en-GB')}.</>}
        </p>
        <div className="mnt-actions">
          <button type="button" className="mnt-retry" onClick={check}>Check now</button>
          <button type="button" className="mnt-retry" onClick={() => setHiddenUntil(Date.now() + 2 * 60 * 1000)}>Hide for 2 min</button>
        </div>
      </div>
    </div>
  );
}
