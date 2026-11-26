// Supplier mail import: which suppliers of this warehouse are imported from
// the tenant mailbox (the mailbox itself is set up in Settings >
// TenantMailSettings). The backend polls the
// mailbox and imports each switched-on supplier's newest Excel attachment
// with the column mapping saved by a manual Excel import, so a supplier needs
// one manual import before mail import can work ("Mapping" column).
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  getMailConfig,
  listMailSuppliers,
  saveMailSupplier,
  pullMailSupplier,
  runMailImport,
  mailImportLog,
} from '../../services/supplierStockService.js';

const STATUS_LABEL = {
  IMPORTED: 'Imported',
  NEEDS_MAPPING: 'Needs mapping',
  FAILED: 'Failed',
  PROCESSING: 'Importing…',
  SUPERSEDED: 'Superseded',
  NO_ATTACHMENT: 'No Excel',
};

function fmt(value) {
  if (!value) return '';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString();
}

function StatusChip({ status }) {
  if (!status) return <span className="ntm-mail-import__muted">—</span>;
  return <span className={`ntm-mail-import__chip is-${String(status).toLowerCase()}`}>{STATUS_LABEL[status] || status}</span>;
}

function MailboxStatus({ tenantId }) {
  const [config, setConfig] = useState(null);
  useEffect(() => {
    let cancelled = false;
    getMailConfig(tenantId).then((data) => { if (!cancelled) setConfig(data); }).catch(() => {});
    return () => { cancelled = true; };
  }, [tenantId]);
  if (!config) return null;
  return (
    <div className="ntm-mail-import__mailbox">
      {config.enabled && config.username
        ? <>Mailbox <strong>{config.username}</strong> · checked every {config.poll_minutes} min{config.last_poll_at ? ` · last ${fmt(config.last_poll_at)}` : ''}</>
        : <span className="ntm-supplier-stock__import-status is-error">Tenant mailbox is not connected - nothing will be imported.</span>}
      {' '}<Link to="/settings">Mailbox settings</Link>
      {config.last_poll_status && config.last_poll_status !== 'OK' ? <div className="ntm-mail-import__muted">{config.last_poll_message}</div> : null}
    </div>
  );
}

function SupplierRow({ row, tenantId, storeId, onSaved, onPulled }) {
  const [draft, setDraft] = useState({ enabled: row.enabled, mail_from: row.mail_from, subject_filter: row.subject_filter, all_stores: row.all_stores });
  const [state, setState] = useState({ state: 'idle', message: '' });
  const dirty = draft.enabled !== row.enabled || draft.mail_from !== row.mail_from || draft.subject_filter !== row.subject_filter
    || draft.all_stores !== row.all_stores;

  async function save(next = draft) {
    setState({ state: 'loading', message: '' });
    try {
      await saveMailSupplier({ tenant_id: tenantId, store_id: storeId, supplier_code: row.supplier_code, ...next });
      setState({ state: 'ok', message: 'Saved' });
      onSaved(row.supplier_code, next);
    } catch (err) {
      setDraft({ enabled: row.enabled, mail_from: row.mail_from, subject_filter: row.subject_filter, all_stores: row.all_stores });
      setState({ state: 'error', message: err.message });
    }
  }

  async function pull() {
    setState({ state: 'loading', message: 'Reading mail…' });
    try {
      const result = await pullMailSupplier(tenantId, storeId, row.supplier_code);
      const ok = result.status === 'IMPORTED';
      setState({ state: ok ? 'ok' : 'error', message: result.supplier?.message || result.message });
      onPulled?.();
    } catch (err) {
      setState({ state: 'error', message: err.message });
    }
  }

  function toggle(event) {
    // Switching a supplier on defaults to importing into all stores.
    const next = { ...draft, enabled: event.target.checked, all_stores: event.target.checked && !row.enabled ? true : draft.all_stores };
    setDraft(next);
    save(next);
  }

  const effective = draft.mail_from || row.master_email;

  return (
    <tr className={draft.enabled ? 'is-on' : ''}>
      <td><input type="checkbox" checked={draft.enabled} onChange={toggle} disabled={state.state === 'loading'} title="Import this supplier's stock from mail" /></td>
      <td>
        <div>{row.supplier_name || row.supplier_code}</div>
        <div className="ntm-mail-import__muted">{row.supplier_code}</div>
      </td>
      <td className="ntm-mail-import__email">{row.master_email || <span className="ntm-mail-import__muted">none</span>}</td>
      <td>
        <input
          type="text"
          value={draft.mail_from}
          placeholder={row.master_email ? 'Use supplier master' : 'Enter supplier mail id'}
          onChange={(e) => setDraft({ ...draft, mail_from: e.target.value })}
        />
      </td>
      <td><input type="text" value={draft.subject_filter} placeholder="Any subject" onChange={(e) => setDraft({ ...draft, subject_filter: e.target.value })} /></td>
      <td>
        <input
          type="checkbox"
          checked={Boolean(draft.all_stores)}
          onChange={(e) => setDraft({ ...draft, all_stores: e.target.checked })}
          title="Import the file into every store of this tenant that has this supplier code"
        />
      </td>
      <td>
        {row.has_mapping === null ? <span className="ntm-mail-import__muted">?</span>
          : row.has_mapping ? <span className="ntm-mail-import__chip is-imported">Saved</span>
            : <span className="ntm-mail-import__chip is-needs_mapping" title="Import one file manually to save the column mapping">Missing</span>}
      </td>
      <td title={row.last?.message || ''}>
        <StatusChip status={row.last?.status} />
        {row.last?.updated_at ? <div className="ntm-mail-import__muted">{fmt(row.last.updated_at)}</div> : null}
      </td>
      <td>
        {dirty ? (
          <button type="button" className="ntm-button ntm-button--primary" disabled={state.state === 'loading'} onClick={() => save()}>Save</button>
        ) : (
          <button
            type="button"
            className="ntm-button"
            disabled={state.state === 'loading' || !effective}
            title={effective ? "Read this supplier's newest stock mail now and update supplier stock" : 'Enter a mail id first'}
            onClick={pull}
          >
            Pull stock
          </button>
        )}
        {state.message ? <div className={`ntm-supplier-stock__import-status is-${state.state}`}>{state.message}</div> : null}
        {draft.enabled && !effective ? <div className="ntm-supplier-stock__import-status is-error">No mail id</div> : null}
      </td>
    </tr>
  );
}

export function SupplierMailImport({ tenantId, storeId }) {
  const [suppliers, setSuppliers] = useState([]);
  const [listState, setListState] = useState({ state: 'loading', message: '' });
  const [search, setSearch] = useState('');
  const [onlyOn, setOnlyOn] = useState(false);
  const [log, setLog] = useState([]);
  const [run, setRun] = useState({ state: 'idle', message: '' });

  const loadSuppliers = useCallback(() => {
    setListState({ state: 'loading', message: 'Loading suppliers…' });
    listMailSuppliers(tenantId, storeId)
      .then((rows) => { setSuppliers(rows); setListState({ state: 'idle', message: '' }); })
      .catch((err) => setListState({ state: 'error', message: err.message }));
  }, [tenantId, storeId]);

  const loadLog = useCallback(() => {
    mailImportLog(tenantId, storeId, 30).then(setLog).catch(() => setLog([]));
  }, [tenantId, storeId]);

  useEffect(() => { loadSuppliers(); loadLog(); }, [loadSuppliers, loadLog]);

  function handleSaved(code, values) {
    setSuppliers((rows) => rows.map((r) => (r.supplier_code === code ? { ...r, ...values } : r)));
  }

  async function checkNow() {
    setRun({ state: 'loading', message: 'Checking the mailbox… this can take a minute.' });
    try {
      const result = await runMailImport(tenantId);
      setRun({ state: result.ok ? 'ok' : 'error', message: result.message });
    } catch (err) {
      setRun({ state: 'error', message: err.message });
    }
    loadSuppliers();
    loadLog();
  }

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    return suppliers.filter((s) => (!onlyOn || s.enabled) && (!q
      || String(s.supplier_name).toLowerCase().includes(q)
      || String(s.supplier_code).toLowerCase().includes(q)
      || String(s.master_email).toLowerCase().includes(q)
      || String(s.mail_from).toLowerCase().includes(q)));
  }, [suppliers, search, onlyOn]);

  const onCount = suppliers.filter((s) => s.enabled).length;

  return (
    <div className="ntm-supplier-stock__import ntm-mail-import">
      <MailboxStatus key={run.message} tenantId={tenantId} />

      <section className="ntm-mail-import__section">
        <header>
          <h3>Suppliers imported from mail ({onCount} on)</h3>
          <span className="ntm-mail-import__muted">
            Mail id comes from the supplier master; type one only to override it. The newest mail with an Excel file replaces that supplier&apos;s stock.
          </span>
        </header>
        <div className="ntm-supplier-stock__toolbar">
          <label>
            Find supplier
            <input type="text" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Name, code or mail id…" />
          </label>
          <label className="ntm-supplier-stock__checkbox">
            <input type="checkbox" checked={onlyOn} onChange={(e) => setOnlyOn(e.target.checked)} />
            Switched on only
          </label>
          <button type="button" className="ntm-button ntm-button--primary" disabled={run.state === 'loading'} onClick={checkNow}>
            Check mail now
          </button>
          <span className={`ntm-supplier-stock__import-status is-${run.state}`}>{run.message}</span>
        </div>
        {listState.state === 'error' ? <div className="ntm-supplier-stock__import-status is-error">{listState.message}</div> : null}
        <div className="ntm-mail-import__table-wrap">
          <table className="ntm-mail-import__table">
            <thead>
              <tr>
                <th>On</th><th>Supplier</th><th>Master mail id</th><th>Mail id override</th>
                <th>Subject contains</th><th>All stores</th><th>Mapping</th><th>Last mail</th><th />
              </tr>
            </thead>
            <tbody>
              {visible.map((row) => (
                <SupplierRow
                  key={row.supplier_code}
                  row={row}
                  tenantId={tenantId}
                  storeId={storeId}
                  onSaved={handleSaved}
                  onPulled={() => { loadSuppliers(); loadLog(); }}
                />
              ))}
              {!visible.length && listState.state !== 'loading' ? (
                <tr><td colSpan={9} className="ntm-mail-import__muted">No suppliers match.</td></tr>
              ) : null}
              {listState.state === 'loading' ? (
                <tr><td colSpan={9} className="ntm-mail-import__muted">{listState.message}</td></tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <section className="ntm-mail-import__section">
        <header>
          <h3>Recent mail imports</h3>
          <button type="button" className="ntm-button" onClick={loadLog}>Refresh</button>
        </header>
        <div className="ntm-mail-import__table-wrap is-short">
          <table className="ntm-mail-import__table">
            <thead>
              <tr><th>When</th><th>Supplier</th><th>Mail</th><th>File</th><th>Result</th><th>Details</th></tr>
            </thead>
            <tbody>
              {log.map((row) => (
                <tr key={row.log_id}>
                  <td>{fmt(row.updated_at)}</td>
                  <td>{row.supplier_code}</td>
                  <td>
                    <div>{row.mail_subject}</div>
                    <div className="ntm-mail-import__muted">{row.mail_from} · {fmt(row.mail_date)}</div>
                  </td>
                  <td>{row.attachment_name}</td>
                  <td><StatusChip status={row.status} /></td>
                  <td>{row.message}</td>
                </tr>
              ))}
              {!log.length ? <tr><td colSpan={6} className="ntm-mail-import__muted">No mail imported yet.</td></tr> : null}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
