// Supplier mail import (backend/modules/supplier_mail_import): the tenant's
// mailbox + which suppliers of this warehouse are imported from mail, a
// per-supplier "Pull stock" and the recent-import log. Same backend contract
// as NexTech MediQ's TenantMailSettings + SupplierMailImport.
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from './api/client.js';

const PROVIDERS = [
  { id: 'gmail', label: 'Gmail / Google Workspace', host: 'imap.gmail.com', hint: '2-Step Verification on, then Google Account > Security > App passwords.' },
  { id: 'zoho', label: 'Zoho Mail (India)', host: 'imap.zoho.in', hint: 'Enable IMAP access in Zoho Mail settings; use an application-specific password.' },
  { id: 'yahoo', label: 'Yahoo Mail', host: 'imap.mail.yahoo.com', hint: 'Yahoo Account Security > Generate app password.' },
  { id: 'outlook', label: 'Outlook / Microsoft 365', host: 'outlook.office365.com', hint: 'Microsoft usually blocks password sign-in for IMAP - prefer Gmail/Zoho.' },
  { id: 'other', label: 'Other mail server', host: '', hint: 'Ask your provider for the IMAP server (port 993, SSL).' },
];

const STATUS_LABEL = {
  IMPORTED: 'Imported', NEEDS_MAPPING: 'Needs mapping', FAILED: 'Failed', PROCESSING: 'Importing...',
  SUPERSEDED: 'Superseded', NO_ATTACHMENT: 'No Excel',
};

const EMPTY = {
  enabled: false, imap_host: 'imap.gmail.com', imap_port: 993, use_ssl: true, username: '', password: '',
  folder: 'INBOX', poll_minutes: 15, lookback_days: 2, daily_time: '08:00',
};

function fmt(value) {
  if (!value) return '';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString();
}

function Chip({ status }) {
  if (!status) return <span className="mail-import-muted">-</span>;
  return <span className={`mail-import-chip is-${String(status).toLowerCase()}`}>{STATUS_LABEL[status] || status}</span>;
}

function Mailbox({ session, tenantId }) {
  const [config, setConfig] = useState(EMPTY);
  const [meta, setMeta] = useState(null);
  const [status, setStatus] = useState({ state: 'loading', message: 'Loading mailbox...' });

  useEffect(() => {
    let cancelled = false;
    api.mailImportConfig(tenantId, session)
      .then((data) => {
        if (cancelled) return;
        setConfig({ ...EMPTY, ...data, password: '' });
        setMeta(data);
        setStatus({ state: 'idle', message: '' });
      })
      .catch((err) => { if (!cancelled) setStatus({ state: 'error', message: err.message }); });
    return () => { cancelled = true; };
  }, [tenantId, session]);

  const set = (key) => (e) => {
    const value = e.target.type === 'checkbox' ? e.target.checked : e.target.value;
    setConfig((c) => ({ ...c, [key]: value }));
  };
  const provider = PROVIDERS.find((p) => p.host && p.host === config.imap_host)?.id || (config.imap_host ? 'other' : 'gmail');
  const daily = Boolean(config.daily_time);
  const payload = () => ({
    ...config,
    imap_port: Number(config.imap_port) || 993,
    poll_minutes: Number(config.poll_minutes) || 15,
    lookback_days: Number(config.lookback_days) || 2,
    password: config.password || null,
  });

  async function run(label, fn) {
    setStatus({ state: 'loading', message: label });
    try {
      const result = await fn();
      return result;
    } catch (err) {
      setStatus({ state: 'error', message: err.message });
      return null;
    }
  }

  async function save() {
    const data = await run('Saving...', () => api.saveMailImportConfig(tenantId, payload(), session));
    if (!data) return;
    setConfig({ ...EMPTY, ...data, password: '' });
    setMeta(data);
    setStatus({ state: 'ok', message: data.enabled ? 'Saved. Mail import is on.' : 'Saved. Mail import is off.' });
  }

  async function test() {
    const result = await run('Signing in to the mailbox...', () => api.testMailImportConfig(tenantId, payload(), session));
    if (result) setStatus({ state: result.ok ? 'ok' : 'error', message: result.message });
  }

  return (
    <section className="mail-import-section">
      <h3>Tenant mailbox</h3>
      <p className="mail-import-muted">One mailbox for the tenant. Mails are only read - never marked read, moved or deleted.</p>
      <div className="mail-import-form">
        <label>Provider
          <select
            value={provider}
            onChange={(e) => {
              const p = PROVIDERS.find((x) => x.id === e.target.value);
              if (p?.host) setConfig((c) => ({ ...c, imap_host: p.host, imap_port: 993, use_ssl: true }));
            }}
          >
            {PROVIDERS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
          </select>
        </label>
        <label>IMAP server<input value={config.imap_host} onChange={set('imap_host')} /></label>
        <label>Port<input type="number" value={config.imap_port} onChange={set('imap_port')} /></label>
        <label>Mail id<input value={config.username} onChange={set('username')} placeholder="stock@company.com" autoComplete="off" /></label>
        <label>App password
          <input type="password" value={config.password} onChange={set('password')} autoComplete="new-password"
            placeholder={meta?.has_password ? 'Saved - leave blank to keep' : 'App password'} />
        </label>
        <label>Import
          <select value={daily ? 'daily' : 'interval'}
            onChange={(e) => setConfig((c) => ({ ...c, daily_time: e.target.value === 'daily' ? (c.daily_time || '08:00') : '' }))}>
            <option value="daily">Every morning</option>
            <option value="interval">Every few minutes</option>
          </select>
        </label>
        {daily
          ? <label>At<input type="time" value={config.daily_time} onChange={set('daily_time')} /></label>
          : <label>Every (min)<input type="number" min="5" value={config.poll_minutes} onChange={set('poll_minutes')} /></label>}
        <label>Look back (days)<input type="number" min="1" max="30" value={config.lookback_days} onChange={set('lookback_days')} /></label>
        <label className="mail-import-check"><input type="checkbox" checked={config.use_ssl} onChange={set('use_ssl')} /> SSL</label>
        <label className="mail-import-check"><input type="checkbox" checked={config.enabled} onChange={set('enabled')} /> Mail import on</label>
      </div>
      <p className="mail-import-muted">{PROVIDERS.find((p) => p.id === provider)?.hint}
        {daily ? ` Imports once a day at ${config.daily_time}; if the PC is switched on later, within a minute of the backend starting.` : ''}</p>
      <div className="mail-import-actions">
        <button type="button" className="secondary-button" disabled={status.state === 'loading'} onClick={test}>Test connection</button>
        <button type="button" className="primary-button" disabled={status.state === 'loading'} onClick={save}>Save mailbox</button>
        <span className={`mail-import-status is-${status.state}`}>{status.message}</span>
      </div>
      {meta?.last_poll_at ? (
        <p className="mail-import-muted">
          Last check {fmt(meta.last_poll_at)} ({meta.last_poll_status}): {meta.last_poll_message}
          {meta.last_daily_run ? ` · Morning import done for ${meta.last_daily_run}` : ''}
        </p>
      ) : null}
    </section>
  );
}

function SupplierRow({ row, session, tenantId, storeId, onChanged }) {
  const pick = (r) => ({ enabled: r.enabled, mail_from: r.mail_from, subject_filter: r.subject_filter, all_stores: r.all_stores });
  const [draft, setDraft] = useState(pick(row));
  const [state, setState] = useState({ state: 'idle', message: '' });
  const dirty = JSON.stringify(draft) !== JSON.stringify(pick(row));
  const effective = draft.mail_from || row.master_email;

  async function save(next = draft) {
    setState({ state: 'loading', message: '' });
    try {
      await api.saveMailImportSupplier({ tenant_id: tenantId, store_id: storeId, supplier_code: row.supplier_code, ...next }, session);
      setState({ state: 'ok', message: 'Saved' });
      onChanged(row.supplier_code, next);
    } catch (err) {
      setDraft(pick(row));
      setState({ state: 'error', message: err.message });
    }
  }

  async function pull() {
    setState({ state: 'loading', message: 'Reading mail...' });
    try {
      const result = await api.pullMailImportSupplier(tenantId, storeId, row.supplier_code, session);
      setState({ state: result.status === 'IMPORTED' ? 'ok' : 'error', message: result.supplier?.message || result.message });
      onChanged(row.supplier_code, null);
    } catch (err) {
      setState({ state: 'error', message: err.message });
    }
  }

  return (
    <tr className={draft.enabled ? 'is-on' : ''}>
      <td>
        <input type="checkbox" checked={draft.enabled} disabled={state.state === 'loading'}
          onChange={(e) => {
            // Switching a supplier on defaults to importing into all stores.
            const next = { ...draft, enabled: e.target.checked, all_stores: e.target.checked && !row.enabled ? true : draft.all_stores };
            setDraft(next);
            save(next);
          }} />
      </td>
      <td>{row.supplier_name || row.supplier_code}<div className="mail-import-muted">{row.supplier_code}</div></td>
      <td>{row.master_email || <span className="mail-import-muted">none</span>}</td>
      <td><input value={draft.mail_from} placeholder={row.master_email ? 'Use supplier master' : 'Supplier mail id'}
        onChange={(e) => setDraft({ ...draft, mail_from: e.target.value })} /></td>
      <td><input value={draft.subject_filter} placeholder="Any subject" onChange={(e) => setDraft({ ...draft, subject_filter: e.target.value })} /></td>
      <td><input type="checkbox" checked={Boolean(draft.all_stores)} title="Import into every store with this supplier code"
        onChange={(e) => setDraft({ ...draft, all_stores: e.target.checked })} /></td>
      <td>{row.has_mapping === null ? '?' : row.has_mapping
        ? <span className="mail-import-chip is-imported">Saved</span>
        : <span className="mail-import-chip is-needs_mapping" title="Import one file manually to save the column mapping">Missing</span>}</td>
      <td title={row.last?.message || ''}><Chip status={row.last?.status} /><div className="mail-import-muted">{fmt(row.last?.updated_at)}</div></td>
      <td>
        {dirty
          ? <button type="button" className="primary-button" disabled={state.state === 'loading'} onClick={() => save()}>Save</button>
          : <button type="button" className="secondary-button" disabled={state.state === 'loading' || !effective}
              title={effective ? "Read this supplier's newest stock mail now and update supplier stock" : 'Enter a mail id first'}
              onClick={pull}>Pull stock</button>}
        {state.message ? <div className={`mail-import-status is-${state.state}`}>{state.message}</div> : null}
      </td>
    </tr>
  );
}

export function SupplierMailImport({ session, tenantId, storeId, onImported }) {
  const [rows, setRows] = useState([]);
  const [listState, setListState] = useState({ state: 'loading', message: 'Loading suppliers...' });
  const [search, setSearch] = useState('');
  const [onlyOn, setOnlyOn] = useState(false);
  const [log, setLog] = useState([]);

  const load = useCallback(() => {
    if (!tenantId || !storeId) return;
    api.mailImportSuppliers(tenantId, storeId, session)
      .then((data) => { setRows(data.suppliers || []); setListState({ state: 'idle', message: '' }); })
      .catch((err) => setListState({ state: 'error', message: err.message }));
    api.mailImportLog(tenantId, storeId, session).then((data) => setLog(data.rows || [])).catch(() => setLog([]));
  }, [tenantId, storeId, session]);

  useEffect(() => { load(); }, [load]);

  function changed(code, values) {
    if (values) setRows((rs) => rs.map((r) => (r.supplier_code === code ? { ...r, ...values } : r)));
    else { load(); onImported?.(); }
  }

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rows.filter((r) => (!onlyOn || r.enabled) && (!q || [r.supplier_name, r.supplier_code, r.master_email, r.mail_from]
      .some((v) => String(v || '').toLowerCase().includes(q))));
  }, [rows, search, onlyOn]);

  if (!tenantId || !storeId) return <div className="mail-import-panel">Select a warehouse first.</div>;

  return (
    <div className="mail-import-panel">
      <Mailbox session={session} tenantId={tenantId} />

      <section className="mail-import-section">
        <h3>Suppliers imported from mail ({rows.filter((r) => r.enabled).length} on)</h3>
        <p className="mail-import-muted">Mail id comes from the supplier master; type one only to override it.
          Only the supplier&apos;s saved column mapping is used.</p>
        <div className="mail-import-actions">
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Find supplier, code or mail id..." />
          <label className="mail-import-check"><input type="checkbox" checked={onlyOn} onChange={(e) => setOnlyOn(e.target.checked)} /> Switched on only</label>
        </div>
        {listState.message ? <div className={`mail-import-status is-${listState.state}`}>{listState.message}</div> : null}
        <div className="mail-import-table-wrap">
          <table className="mail-import-table">
            <thead>
              <tr><th>On</th><th>Supplier</th><th>Master mail id</th><th>Mail id override</th><th>Subject contains</th>
                <th>All stores</th><th>Mapping</th><th>Last mail</th><th /></tr>
            </thead>
            <tbody>
              {visible.map((row) => (
                <SupplierRow key={row.supplier_code} row={row} session={session} tenantId={tenantId} storeId={storeId} onChanged={changed} />
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="mail-import-section">
        <h3>Recent mail imports <button type="button" className="secondary-button" onClick={load}>Refresh</button></h3>
        <div className="mail-import-table-wrap is-short">
          <table className="mail-import-table">
            <thead><tr><th>When</th><th>Supplier</th><th>Mail</th><th>File</th><th>Result</th><th>Details</th></tr></thead>
            <tbody>
              {log.map((r) => (
                <tr key={r.log_id}>
                  <td>{fmt(r.updated_at)}</td><td>{r.supplier_code}</td>
                  <td>{r.mail_subject}<div className="mail-import-muted">{r.mail_from} · {fmt(r.mail_date)}</div></td>
                  <td>{r.attachment_name}</td><td><Chip status={r.status} /></td><td>{r.message}</td>
                </tr>
              ))}
              {!log.length ? <tr><td colSpan={6} className="mail-import-muted">No mail imported yet.</td></tr> : null}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
