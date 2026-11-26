// Order Automation Settings -- admin-only (super-admin gated in App.jsx's
// screens array, same pattern as schema_sync/db_monitor). Extracted from the
// old PmOrderEntry.jsx's inline AutomationSettings modal per owner ruling
// 2026-11-24: PM users must never see or infer that automation exists. Same
// backend endpoints (GET/PUT .../automation, .../message-settings) -- no
// server changes, just a standalone screen with its own store picker.
import { useCallback, useEffect, useState } from 'react';
import { api } from './api/client.js';

const MESSAGE_TYPE_LABEL = {
  ORDER_GENERATED: 'Order generated', STOCK_LIST: 'Stock list', TIME_LIST: 'Time list',
  STOCK_READY: 'Stock ready', ENTRY_READY: 'Entry ready',
};

export default function OrderAutomationSettings({ session }) {
  const [stores, setStores] = useState([]);
  const [storeLabels, setStoreLabels] = useState({});
  const [store, setStore] = useState('');
  const [automation, setAutomation] = useState(null);
  const [messages, setMessages] = useState([]);
  const [error, setError] = useState('');
  const [note, setNote] = useState('');
  const [saving, setSaving] = useState(false);
  const [targetDrafts, setTargetDrafts] = useState({});

  useEffect(() => {
    api.legacyStores(session, true)
      .then((rows) => {
        const all = Array.isArray(rows) ? rows : [];
        const list = all.map((r) => r.store_name);
        setStoreLabels(Object.fromEntries(all.map((r) => [r.store_name, r.display_name || r.store_name])));
        setStores(list);
        setStore((cur) => cur || list[0] || '');
      })
      .catch((err) => setError(err.message || 'Could not load stores.'));
  }, [session]);

  const load = useCallback(() => {
    if (!store) return;
    setError('');
    Promise.all([api.legacyOrderAutomation(store, session), api.legacyMessageSettings(store, session)])
      .then(([auto, msgs]) => {
        setAutomation(auto);
        setMessages(msgs);
        setTargetDrafts(Object.fromEntries(msgs.map((m) => [m.message_type, (m.targets || []).map((t) => t.name).join(', ')])));
      })
      .catch((err) => setError(err.message || 'Could not load automation settings.'));
  }, [session, store]);

  useEffect(() => { setAutomation(null); setMessages([]); load(); }, [load]);

  const saveAutomation = async (patch) => {
    setSaving(true);
    setError('');
    setNote('');
    try {
      const next = { ...automation, ...patch };
      const saved = await api.legacySetOrderAutomation(store, {
        automated_order_enabled: next.automated_order_enabled,
        production_mode: next.production_mode,
        min_delay_seconds: next.min_delay_seconds,
        max_delay_seconds: next.max_delay_seconds,
      }, session);
      setAutomation(saved);
      setNote('Saved.');
    } catch (err) {
      setError(err.message || 'Could not save.');
    } finally {
      setSaving(false);
    }
  };

  const saveMessage = async (messageType, enabled) => {
    setSaving(true);
    setError('');
    setNote('');
    try {
      const names = (targetDrafts[messageType] || '').split(',').map((s) => s.trim()).filter(Boolean);
      const targets = names.map((name) => ({ name, kind: 'contact' }));
      const saved = await api.legacySaveMessageSetting(store, messageType, { enabled, targets }, session);
      setMessages((cur) => cur.map((m) => (m.message_type === messageType ? saved : m)));
      setNote('Saved.');
    } catch (err) {
      setError(err.message || 'Could not save.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="screen-panel poe-screen">
      <header className="screen-header">
        <div>
          <h2>Order Automation</h2>
          <p>Automated Order Entry settings and WhatsApp message types, per store. Not visible to PM users.</p>
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
      {note && <div className="status-line lgo-ok">{note}</div>}

      {!automation ? <p className="poe-muted">Loading…</p> : (
        <>
          <section className="poe-card">
            <header className="poe-card-head"><h3>Automation · {store}</h3></header>
            <div className="poe-form">
              <label className="poe-checkbox">
                <input type="checkbox" checked={!!automation.automated_order_enabled} disabled={saving}
                  onChange={(e) => saveAutomation({ automated_order_enabled: e.target.checked })} />
                Automated order entry — queue a random settle delay (1–7 min) and auto-process the
                submitted bill/GRN instead of generating immediately.
              </label>
              <label className="poe-checkbox">
                <input type="checkbox" checked={!!automation.production_mode} disabled={saving}
                  onChange={(e) => saveAutomation({ production_mode: e.target.checked })} />
                Production mode — send real WhatsApp notices (off = test mode, notices are logged only).
              </label>
              <div className="poe-form-row">
                <label><span>Min delay (sec)</span>
                  <input type="number" min={0} value={automation.min_delay_seconds} disabled={saving}
                    onChange={(e) => setAutomation((a) => ({ ...a, min_delay_seconds: Number(e.target.value) }))}
                    onBlur={() => saveAutomation({})} />
                </label>
                <label><span>Max delay (sec)</span>
                  <input type="number" min={0} value={automation.max_delay_seconds} disabled={saving}
                    onChange={(e) => setAutomation((a) => ({ ...a, max_delay_seconds: Number(e.target.value) }))}
                    onBlur={() => saveAutomation({})} />
                </label>
              </div>
            </div>
          </section>

          <section className="poe-card">
            <header className="poe-card-head"><h3>Message types</h3></header>
            <div className="poe-tablewrap">
              <table className="trp-table">
                <thead><tr><th className="trp-left">Type</th><th>Enabled</th><th className="trp-left">Targets (comma-separated)</th><th /></tr></thead>
                <tbody>
                  {messages.map((m) => (
                    <tr key={m.message_type}>
                      <td className="trp-left">{MESSAGE_TYPE_LABEL[m.message_type] || m.message_type}</td>
                      <td><input type="checkbox" checked={!!m.enabled} disabled={saving}
                        onChange={(e) => saveMessage(m.message_type, e.target.checked)} /></td>
                      <td className="trp-left">
                        <input value={targetDrafts[m.message_type] || ''} disabled={saving}
                          placeholder="Group or contact name"
                          onChange={(e) => setTargetDrafts((cur) => ({ ...cur, [m.message_type]: e.target.value }))} />
                      </td>
                      <td>
                        <button type="button" className="secondary-button" disabled={saving}
                          onClick={() => saveMessage(m.message_type, m.enabled)}>Save</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </section>
  );
}
