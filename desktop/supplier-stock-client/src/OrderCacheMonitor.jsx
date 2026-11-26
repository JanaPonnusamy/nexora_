// Order Cache Monitor -- platform-admin view of each store's local SQLite
// order cache: file age, row count, edits not yet written back to HO, last
// write-back status, connection status. Port of the web/MediQ page
// (frontend/src/components/sync/OrderCacheMonitor.tsx); the force actions
// (pull/push/export/send/import) hit the same backend routes the automatic
// Order Process path uses, so a manual drain behaves exactly like an
// automatic one.
import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from './api/client.js';

function ageLabel(seconds) {
  if (seconds == null) return '—';
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

function fmtDateTime(value) {
  if (!value) return '—';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString();
}

export default function OrderCacheMonitor({ session }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState('');
  const [note, setNote] = useState('');
  const [importTarget, setImportTarget] = useState(null);
  const fileInputRef = useRef(null);
  const mounted = useRef(true);

  useEffect(() => () => { mounted.current = false; }, []);

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    return api.orderCacheMonitor(session)
      .then((data) => { if (mounted.current) setRows(data?.stores || []); })
      .catch((err) => { if (mounted.current) setError(err.message || 'Could not load order cache status.'); })
      .finally(() => { if (mounted.current) setLoading(false); });
  }, [session]);

  useEffect(() => { load(); }, [load]);

  const withBusy = async (key, fn) => {
    setBusy(key);
    setError('');
    setNote('');
    try {
      const msg = await fn();
      if (mounted.current) setNote(msg);
      await load();
    } catch (err) {
      if (mounted.current) setError(err.message || 'Action failed.');
    } finally {
      if (mounted.current) setBusy(null);
    }
  };

  const forcePull = (store) => withBusy(`pull:${store}`, async () => {
    await api.orderCacheForcePull(store, session);
    return `${store}: cache rebuilt from central.`;
  });

  const forcePush = (store) => withBusy(`push:${store}`, async () => {
    const result = await api.orderCacheForcePush(store, session);
    if (!result?.ok) throw new Error(result?.error || 'Write-back did not drain.');
    return `${store}: ${result.applied} edit(s) pushed to HO.`;
  });

  const exportFile = (store) => withBusy(`export:${store}`, async () => {
    const blob = await api.orderCacheExport(store, session);
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `order_cache_${store}.sqlite`;
    link.click();
    URL.revokeObjectURL(url);
    return `${store}: cache file downloaded.`;
  });

  const sendFile = (store) => withBusy(`send:${store}`, async () => {
    const result = await api.orderCacheSend(store, 'whatsapp', session);
    if (!result?.ok) throw new Error(result?.error || 'Send via WhatsApp failed.');
    return `${store}: cache file sent via WhatsApp.`;
  });

  const openImportPicker = (store) => {
    setImportTarget(store);
    fileInputRef.current?.click();
  };

  const onImportFileChosen = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file || !importTarget) return;
    const store = importTarget;
    setImportTarget(null);
    await withBusy(`import:${store}`, async () => {
      const result = await api.orderCacheImport(store, file, session);
      if (!result?.writeback?.ok) throw new Error(result?.writeback?.error || 'Imported, but write-back did not drain.');
      return `${store}: imported and ${result.writeback.applied} edit(s) pushed to HO.`;
    });
  };

  return (
    <section className="screen-panel poe-screen">
      <header className="screen-header">
        <div>
          <h2>Order Cache Monitor</h2>
          <p>Per-store local SQLite order cache: file age, unsynced edits, last write-back to HO.</p>
        </div>
        <div className="poe-tools">
          <button type="button" className="secondary-button" onClick={load} disabled={loading}>
            {loading ? 'Loading…' : 'Refresh'}
          </button>
        </div>
      </header>

      {error && <div className="status-line error">{error}</div>}
      {note && <div className="status-line lgo-ok">{note}</div>}

      <input ref={fileInputRef} type="file" accept=".sqlite,.db" hidden onChange={onImportFileChosen} />

      <section className="poe-card">
        <header className="poe-card-head">
          <h3>Stores</h3>
          <span className="poe-muted">{rows.length} store(s)</span>
        </header>
        <div className="trp-tablewrap poe-tablewrap">
          <table className="trp-table">
            <thead>
              <tr>
                <th className="trp-left">Store</th><th>File created</th><th>Rows</th><th>Unsynced</th>
                <th className="trp-left">Last write-back</th><th>Connection</th><th />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const store = row.store_name;
                const pending = row.unsynced_row_count ?? 0;
                return (
                  <tr key={store} className={row.exists && pending > 0 ? 'lgo-warn' : ''}>
                    <td className="trp-left"><strong>{store}</strong></td>
                    <td title={row.file_created_at || ''}>{row.exists ? ageLabel(row.file_age_seconds) : <span className="poe-muted">no cache file</span>}</td>
                    <td>{row.exists ? (row.row_count ?? 0).toLocaleString() : '—'}</td>
                    <td>{row.exists ? `${pending} pending` : '—'}</td>
                    <td className="trp-left">
                      {row.exists ? `${row.last_writeback_status || 'never'} · ${fmtDateTime(row.last_writeback_at)}` : '—'}
                      {row.last_writeback_error && <><br /><span className="error">{row.last_writeback_error}</span></>}
                    </td>
                    <td>{row.connection_status || 'ok'}</td>
                    <td>
                      <button type="button" className="secondary-button" title="Force pull: rebuild cache from central now"
                        disabled={busy != null} onClick={() => forcePull(store)}>
                        {busy === `pull:${store}` ? 'Pulling…' : 'Pull'}
                      </button>
                      <button type="button" className="secondary-button" title="Force push: drain pending write-back to HO now"
                        disabled={busy != null} onClick={() => forcePush(store)}>
                        {busy === `push:${store}` ? 'Pushing…' : 'Push'}
                      </button>
                      <button type="button" className="secondary-button" title="Download the raw .sqlite cache file"
                        disabled={busy != null || !row.exists} onClick={() => exportFile(store)}>
                        {busy === `export:${store}` ? 'Exporting…' : 'Export'}
                      </button>
                      <button type="button" className="secondary-button" title="Send cache file via WhatsApp (offline fallback)"
                        disabled={busy != null || !row.exists} onClick={() => sendFile(store)}>
                        {busy === `send:${store}` ? 'Sending…' : 'Send'}
                      </button>
                      <button type="button" className="secondary-button" title="Import a cache file received by mail/WhatsApp"
                        disabled={busy != null} onClick={() => openImportPicker(store)}>
                        {busy === `import:${store}` ? 'Importing…' : 'Import'}
                      </button>
                    </td>
                  </tr>
                );
              })}
              {!loading && !rows.length && (
                <tr><td colSpan={7} className="poe-muted">No active stores, or the order cache feature is disabled on HO (LEGACY_ORDER_CACHE_ENABLED).</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  );
}
