// Tenant mailbox for Supplier Mail Import (backend/modules/supplier_mail_import).
// One IMAP mailbox per tenant; suppliers are switched on per warehouse in
// Supplier Stock > Mail Import. The backend reads mails only (never marks
// read/moves/deletes) and imports each switched-on supplier's newest Excel.
import React, { useEffect, useState } from 'react';
import { getMailConfig, saveMailConfig, testMailConfig, runMailImport } from '../../services/supplierStockService.js';

const EMPTY_CONFIG = {
  enabled: false, imap_host: '', imap_port: 993, use_ssl: true, username: '', password: '',
  folder: 'INBOX', poll_minutes: 15, lookback_days: 2, daily_time: '08:00',
};

const PROVIDERS = [
  {
    id: 'gmail', label: 'Gmail / Google Workspace', host: 'imap.gmail.com', port: 993,
    hint: 'Turn on 2-Step Verification for the Google account, then create an App password (Google Account > Security > App passwords) and paste it below. IMAP is on by default.',
  },
  {
    id: 'zoho', label: 'Zoho Mail (India)', host: 'imap.zoho.in', port: 993,
    hint: 'Zoho Mail > Settings > Mail Accounts > IMAP Access: enable IMAP. With 2FA on, create an application-specific password. Use imap.zoho.com for non-India accounts.',
  },
  {
    id: 'outlook', label: 'Outlook / Microsoft 365', host: 'outlook.office365.com', port: 993,
    hint: 'Microsoft has switched off password (basic) sign-in for IMAP on most Microsoft 365 tenants. If Test connection fails with a sign-in error, use a Gmail/Zoho mailbox or forward supplier mails to one.',
  },
  {
    id: 'yahoo', label: 'Yahoo Mail', host: 'imap.mail.yahoo.com', port: 993,
    hint: 'Yahoo Account Security > Generate app password, and use that here.',
  },
  { id: 'other', label: 'Other (company mail server)', host: '', port: 993, hint: 'Ask your mail provider for the IMAP server name and port (993 with SSL is usual).' },
];

function providerFor(host) {
  return PROVIDERS.find((p) => p.host && p.host === String(host || '').trim().toLowerCase())?.id || (host ? 'other' : 'gmail');
}

function fmt(value) {
  if (!value) return '';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString();
}

export function TenantMailSettings({ tenantId, tenantName }) {
  const [config, setConfig] = useState(EMPTY_CONFIG);
  const [meta, setMeta] = useState(null);
  const [provider, setProvider] = useState('gmail');
  const [status, setStatus] = useState({ state: 'loading', message: 'Loading mailbox…' });

  useEffect(() => {
    if (!tenantId) return undefined;
    let cancelled = false;
    setStatus({ state: 'loading', message: 'Loading mailbox…' });
    getMailConfig(tenantId)
      .then((data) => {
        if (cancelled) return;
        setConfig({ ...EMPTY_CONFIG, ...data, password: '' });
        setMeta(data);
        setProvider(providerFor(data.imap_host));
        setStatus({ state: 'idle', message: '' });
      })
      .catch((err) => { if (!cancelled) setStatus({ state: 'error', message: err.message }); });
    return () => { cancelled = true; };
  }, [tenantId]);

  const update = (key) => (event) => {
    const value = event.target.type === 'checkbox' ? event.target.checked : event.target.value;
    setConfig((c) => ({ ...c, [key]: value }));
  };

  function chooseProvider(id) {
    setProvider(id);
    const preset = PROVIDERS.find((p) => p.id === id);
    if (preset?.host) setConfig((c) => ({ ...c, imap_host: preset.host, imap_port: preset.port, use_ssl: true }));
  }

  function payload() {
    return {
      ...config,
      imap_port: Number(config.imap_port) || 993,
      poll_minutes: Number(config.poll_minutes) || 15,
      lookback_days: Number(config.lookback_days) || 2,
      password: config.password || null,
    };
  }

  const daily = Boolean(config.daily_time);

  async function save() {
    setStatus({ state: 'loading', message: 'Saving…' });
    try {
      const data = await saveMailConfig(tenantId, payload());
      setConfig({ ...EMPTY_CONFIG, ...data, password: '' });
      setMeta(data);
      setStatus({ state: 'ok', message: data.enabled ? 'Saved. Mail import is on.' : 'Saved. Mail import is off.' });
    } catch (err) {
      setStatus({ state: 'error', message: err.message });
    }
  }

  async function test() {
    setStatus({ state: 'loading', message: 'Signing in to the mailbox…' });
    try {
      const result = await testMailConfig(tenantId, payload());
      setStatus({ state: result.ok ? 'ok' : 'error', message: result.message });
    } catch (err) {
      setStatus({ state: 'error', message: err.message });
    }
  }

  async function checkNow() {
    setStatus({ state: 'loading', message: 'Checking the mailbox… this can take a minute.' });
    try {
      const result = await runMailImport(tenantId);
      setStatus({ state: result.ok ? 'ok' : 'error', message: result.message });
      setMeta(await getMailConfig(tenantId));
    } catch (err) {
      setStatus({ state: 'error', message: err.message });
    }
  }

  if (!tenantId) {
    return <div className="ntm-card ntm-form"><p className="ntm-form__hint">Select a tenant in the header to set up its mailbox.</p></div>;
  }

  const busy = status.state === 'loading';
  const hint = PROVIDERS.find((p) => p.id === provider)?.hint;

  return (
    <div className="ntm-card ntm-form ntm-mail-settings">
      <p className="ntm-form__hint">
        One mailbox for <strong>{tenantName || 'this tenant'}</strong>. Suppliers send their stock Excel to this mailbox;
        switch each supplier on in Supplier Stock &gt; Mail Import. Mails are only read - never marked read, moved or deleted.
      </p>

      <div className="ntm-field">
        <label htmlFor="ntm-mail-provider">Mail provider</label>
        <select id="ntm-mail-provider" value={provider} onChange={(e) => chooseProvider(e.target.value)}>
          {PROVIDERS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
        </select>
        {hint ? <span className="ntm-form__hint">{hint}</span> : null}
      </div>

      <div className="ntm-mail-settings__row">
        <div className="ntm-field ntm-mail-settings__grow">
          <label htmlFor="ntm-mail-host">IMAP server</label>
          <input id="ntm-mail-host" type="text" value={config.imap_host} onChange={update('imap_host')} placeholder="imap.gmail.com" />
        </div>
        <div className="ntm-field ntm-mail-settings__small">
          <label htmlFor="ntm-mail-port">Port</label>
          <input id="ntm-mail-port" type="number" value={config.imap_port} onChange={update('imap_port')} />
        </div>
      </div>

      <div className="ntm-field">
        <label htmlFor="ntm-mail-user">Mail id (username)</label>
        <input id="ntm-mail-user" type="text" value={config.username} onChange={update('username')} placeholder="stock@yourcompany.com" autoComplete="off" />
      </div>
      <div className="ntm-field">
        <label htmlFor="ntm-mail-pass">App password</label>
        <input
          id="ntm-mail-pass"
          type="password"
          value={config.password}
          onChange={update('password')}
          placeholder={meta?.has_password ? 'Saved - leave blank to keep' : 'App password'}
          autoComplete="new-password"
        />
      </div>

      <div className="ntm-mail-settings__row">
        <div className="ntm-field">
          <label htmlFor="ntm-mail-schedule">Import</label>
          <select
            id="ntm-mail-schedule"
            value={daily ? 'daily' : 'interval'}
            onChange={(e) => setConfig((c) => ({ ...c, daily_time: e.target.value === 'daily' ? (c.daily_time || '08:00') : '' }))}
          >
            <option value="daily">Every morning</option>
            <option value="interval">Every few minutes</option>
          </select>
        </div>
        {daily ? (
          <div className="ntm-field ntm-mail-settings__small">
            <label htmlFor="ntm-mail-time">At</label>
            <input id="ntm-mail-time" type="time" value={config.daily_time} onChange={update('daily_time')} />
          </div>
        ) : (
          <div className="ntm-field ntm-mail-settings__small">
            <label htmlFor="ntm-mail-every">Check every (min)</label>
            <input id="ntm-mail-every" type="number" min="5" value={config.poll_minutes} onChange={update('poll_minutes')} />
          </div>
        )}
        <div className="ntm-field ntm-mail-settings__small">
          <label htmlFor="ntm-mail-back">Look back (days)</label>
          <input id="ntm-mail-back" type="number" min="1" max="30" value={config.lookback_days} onChange={update('lookback_days')} />
        </div>
        <div className="ntm-field">
          <label htmlFor="ntm-mail-folder">Folder</label>
          <input id="ntm-mail-folder" type="text" value={config.folder} onChange={update('folder')} />
        </div>
      </div>
      {daily ? (
        <span className="ntm-form__hint">
          Imports once a day at {config.daily_time}. If this PC is switched on later than that, it imports within a minute
          of the backend starting. Use Pull in Supplier Stock &gt; Mail Import to read a supplier&apos;s mail any time.
        </span>
      ) : null}

      <div className="ntm-mail-settings__row">
        <label className="ntm-mail-settings__check"><input type="checkbox" checked={config.use_ssl} onChange={update('use_ssl')} /> Use SSL</label>
        <label className="ntm-mail-settings__check"><input type="checkbox" checked={config.enabled} onChange={update('enabled')} /> Mail import on for this tenant</label>
      </div>

      <div className="ntm-form__actions">
        <button type="button" className="ntm-button" disabled={busy} onClick={test}>Test connection</button>
        <button type="button" className="ntm-button ntm-button--primary" disabled={busy} onClick={save}>Save</button>
        <button type="button" className="ntm-button" disabled={busy || !meta?.enabled} onClick={checkNow} title={meta?.enabled ? '' : 'Save with mail import on first'}>
          Check mail now
        </button>
      </div>
      {status.message ? <span className={`ntm-mail-settings__status is-${status.state}`}>{status.message}</span> : null}
      {meta?.last_poll_at ? (
        <span className="ntm-form__hint">
          Last check {fmt(meta.last_poll_at)} ({meta.last_poll_status}): {meta.last_poll_message}
          {meta.last_daily_run ? ` · Morning import done for ${meta.last_daily_run}` : ''}
        </span>
      ) : null}
    </div>
  );
}
