// Store-level WhatsApp (renderer side). The WhatsApp Web session itself lives
// in the Electron main process (electron/whatsapp.cjs) on THIS store PC; this
// file is the UI around it:
//   - StoreWhatsAppScreen: link (QR) / unlink, send anything to any chat, log.
//   - WhatsAppSendDialog: "Send on WhatsApp" for an exported order file.
//   - useStoreWhatsAppOutbox: sends the NMW stock files HO queued for this
//     store (distribution whatsapp_sender = STORE) from the store's number.
import { useCallback, useEffect, useRef, useState } from 'react';
import { unzipSync } from 'fflate';
import { api } from './api/client.js';

// Engine (per PC): 'local' = this PC's own WhatsApp window (QR-linked here);
// 'ho' = send through the HO server's already-linked WhatsApp profile
// (/api/whatsapp, e.g. "Jana") -- for the HO PC, so it never needs a second
// login of the same number.
const ENGINE_KEY = 'nexora.desktop.waEngine';
export function whatsAppEngine() {
  try { return localStorage.getItem(ENGINE_KEY) === 'ho' ? 'ho' : 'local'; } catch { return 'local'; }
}
export function setWhatsAppEngine(engine) {
  try { localStorage.setItem(ENGINE_KEY, engine === 'ho' ? 'ho' : 'local'); } catch { /* per-PC preference */ }
}

let hoSession = null;
let hoProfile = null; // { profile_id, profile_name }
let hoChats = { at: 0, chats: [] };
// App passes the signed-in session so the HO engine can call the API.
export function setWhatsAppSession(session) {
  if (session?.token !== hoSession?.token) { hoProfile = null; hoChats = { at: 0, chats: [] }; }
  hoSession = session;
}

async function hoProfileId() {
  if (hoProfile) return hoProfile.profile_id;
  const state = await api.hoWhatsAppState(hoSession);
  const profiles = state?.profiles || [];
  hoProfile = profiles.find((p) => p.is_default) || profiles[0] || null;
  if (!hoProfile) throw new Error('No WhatsApp profile is set up on the HO server.');
  return hoProfile.profile_id;
}

const hoBridge = {
  async status() {
    if (!hoSession) return { state: 'off', engine: 'ho' };
    try {
      const id = await hoProfileId();
      const st = await api.hoWhatsAppStatus(id, hoSession);
      return { state: st.state === 'ready' || st.logged_in ? 'ready' : st.state || 'loading', engine: 'ho', profileName: hoProfile?.profile_name || '' };
    } catch (e) {
      return { state: 'error', engine: 'ho', error: e.message };
    }
  },
  async send({ chat, text, paths = [], files = [] }) {
    try {
      const id = await hoProfileId();
      const all = [...(paths.length ? await window.nexoraDesktop.whatsapp.readFiles(paths) : []), ...files];
      const res = all.length
        ? await api.hoWhatsAppSendFiles({ profile_id: id, chat_name: chat, message: text || '', files: all }, hoSession)
        : await api.hoWhatsAppSendText({ profile_id: id, chat_name: chat, message: text || '' }, hoSession);
      return res?.status === 'sent' ? { status: 'sent' } : { status: 'failed', error: res?.message || res?.error || 'Send failed.' };
    } catch (e) {
      return { status: 'failed', error: e.message || 'Send failed.' };
    }
  },
  async chats({ query = '', filter = 'all', refresh = false } = {}) {
    try {
      if (refresh || !hoChats.chats.length || Date.now() - hoChats.at > 10 * 60000) {
        const res = await api.hoWhatsAppChats(await hoProfileId(), hoSession);
        hoChats = { at: Date.now(), chats: res?.chats || [] };
      }
      const q = query.trim().toLowerCase();
      return {
        chats: hoChats.chats.filter((c) => (!q || c.name.toLowerCase().includes(q))
          && (filter === 'all' || (filter === 'groups' ? c.kind === 'group' : c.kind === 'contact'))),
      };
    } catch (e) {
      return { chats: [], error: e.message };
    }
  },
  async log() {
    const res = await api.hoWhatsAppLog(hoSession);
    return (res?.entries || []).map((e) => ({
      at: e.at, chat: e.target_name, files: [], text: e.message_preview, source: e.profile_name ? `HO · ${e.profile_name}` : 'HO',
      status: e.status === 'sent' ? 'sent' : 'failed', error: e.error,
    }));
  },
};

const wa = () => {
  const local = window.nexoraDesktop?.whatsapp;
  if (!local) return null;
  return whatsAppEngine() === 'ho' ? hoBridge : local;
};
export const storeWhatsAppAvailable = () => Boolean(wa());

const RECENT_KEY = 'store-wa-recent-chats';
const chatKey = (key) => `store-wa-chat:${key}`;

function readRecent() {
  try { return JSON.parse(localStorage.getItem(RECENT_KEY) || '[]').filter(Boolean); } catch { return []; }
}
function rememberChat(rememberKey, chat) {
  try {
    if (rememberKey) localStorage.setItem(chatKey(rememberKey), chat);
    const recent = [chat, ...readRecent().filter((c) => c.toLowerCase() !== chat.toLowerCase())].slice(0, 15);
    localStorage.setItem(RECENT_KEY, JSON.stringify(recent));
  } catch { /* storage unavailable */ }
}
function rememberedChat(rememberKey) {
  try { return rememberKey ? localStorage.getItem(chatKey(rememberKey)) || '' : ''; } catch { return ''; }
}

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve(String(reader.result).split(',')[1] || '');
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

const STATE_TEXT = {
  off: 'Not set up on this PC.',
  starting: 'Starting WhatsApp…',
  loading: 'Loading WhatsApp…',
  qr: 'Not linked — scan the QR code with the store phone.',
  ready: 'Linked and ready to send.',
  error: 'HO WhatsApp could not be reached.'
};
const HO_STATE_TEXT = {
  off: 'Sign in to use the HO WhatsApp.',
  loading: 'HO WhatsApp is loading…',
  qr: 'HO WhatsApp is logged out — scan its QR on the HO WhatsApp page.',
  ready: 'Ready — sending through the HO WhatsApp.',
};

export function useStoreWhatsAppStatus(pollMs = 3000, engine = whatsAppEngine()) {
  const [status, setStatus] = useState({ state: engine === 'ho' ? 'loading' : 'off' });
  const refresh = useCallback(async () => {
    if (!wa()) return;
    try { setStatus(await wa().status()); } catch { /* main process busy */ }
  }, []);
  useEffect(() => {
    if (!wa()) return undefined;
    refresh();
    const timer = setInterval(refresh, engine === 'ho' ? Math.max(pollMs, 30000) : pollMs);
    return () => clearInterval(timer);
  }, [refresh, pollMs, engine]);
  return [status, refresh];
}

function ChatInput({ value, onChange, id }) {
  const recent = readRecent();
  return (
    <>
      <input
        id={id}
        list={`${id}-recent`}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Group / contact name exactly as in WhatsApp, or a phone number"
      />
      <datalist id={`${id}-recent`}>
        {recent.map((c) => <option key={c} value={c} />)}
      </datalist>
    </>
  );
}

// Owner rule: never a .zip on WhatsApp. Images go first, sheets last.
export function sendableFiles(paths) {
  const list = (paths || []).filter((p) => p && !/\.zip$/i.test(p));
  const isImage = (p) => /\.(png|jpe?g)$/i.test(p);
  return [...list.filter(isImage), ...list.filter((p) => !isImage(p))];
}

// Send the same files/text to every target in turn (one group, or several
// contacts). -> { sent: [names], failed: [{ name, error }] }
export async function sendToTargets(targets, { text, paths, files, source }) {
  const sent = [];
  const failed = [];
  for (const t of targets) {
    const name = typeof t === 'string' ? t : t.name;
    const result = await wa().send({ chat: name, text, paths, files, source });
    if (result.status === 'sent') sent.push(name); else failed.push({ name, error: result.error || 'Send failed.' });
  }
  return { sent, failed };
}

// Search this PC's WhatsApp for contacts / groups. Each search drives the
// hidden WhatsApp page, so it runs on Enter / the button, not per keystroke.
export function ChatPicker({ onPick, picked = [] }) {
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('all');
  const [state, setState] = useState({ busy: false, error: '', chats: null });
  const run = async (refresh = false, nextFilter = filter) => {
    setState((cur) => ({ ...cur, busy: true, error: '' }));
    const res = await wa().chats({ query, filter: nextFilter, refresh });
    setState({ busy: false, error: res.error || '', chats: res.chats || [] });
  };
  const pickedNames = new Set(picked.map((p) => p.name.toLowerCase()));
  return (
    <div className="swa-picker">
      <div className="swa-picker-bar">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); run(); } }}
          placeholder="Search WhatsApp contacts and groups"
          aria-label="Search WhatsApp contacts and groups"
        />
        <button type="button" className="secondary-button" onClick={() => run()} disabled={state.busy}>{state.busy ? 'Searching…' : 'Search'}</button>
      </div>
      <div className="swa-picker-tabs" role="tablist" aria-label="Chat type">
        {[['all', 'All'], ['groups', 'Groups'], ['contacts', 'Contacts']].map(([key, label]) => (
          <button key={key} type="button" role="tab" aria-selected={filter === key}
            className={filter === key ? 'is-active' : ''}
            onClick={() => { setFilter(key); if (state.chats) run(false, key); }}>{label}</button>
        ))}
        <button type="button" className="swa-link" onClick={() => run(true)} disabled={state.busy} title="Re-read the group list from WhatsApp">Refresh groups</button>
      </div>
      {state.error && <div className="status-line error">{state.error}</div>}
      {state.chats && (
        <ul className="swa-picker-list">
          {state.chats.length ? state.chats.map((c) => (
            <li key={`${c.kind}:${c.name}`}>
              <button type="button" disabled={pickedNames.has(c.name.toLowerCase())} onClick={() => onPick(c)}>
                <span className={`swa-kind swa-kind-${c.kind}`}>{c.kind === 'group' ? 'Group' : 'Contact'}</span>
                <span className="swa-picker-name">{c.name}</span>
              </button>
            </li>
          )) : <li className="swa-muted">No chats found.</li>}
        </ul>
      )}
    </div>
  );
}

// "Send on WhatsApp" for already-saved files (an order export, a report).
// `targets` (saved supplier contacts) are sent to by default; otherwise the
// chat is remembered per rememberKey (e.g. the supplier code) for next time.
// files: saved paths; blobs: in-memory [{ name, blob }] (a report download).
export function WhatsAppSendDialog({ title, files = [], blobs = [], rememberKey, defaultChat = '', defaultText = '', targets = [], source, onClose, onSent }) {
  const [chat, setChat] = useState(() => (targets.length ? '' : rememberedChat(rememberKey) || defaultChat));
  const [useSaved, setUseSaved] = useState(targets.length > 0);
  const [text, setText] = useState(defaultText);
  const [searching, setSearching] = useState(false);
  const [state, setState] = useState({ busy: false, error: '' });
  const sendFiles = [...sendableFiles(files), ...sendableFiles(blobs.map((b) => b.name))];

  const send = async () => {
    const list = useSaved ? targets : chat.trim() ? [chat.trim()] : [];
    if (!list.length) { setState({ busy: false, error: 'Enter the WhatsApp chat, group or number.' }); return; }
    setState({ busy: true, error: '' });
    const order = sendableFiles(blobs.map((b) => b.name));
    const payloadFiles = await Promise.all(order.map(async (name) => ({ name, base64: await blobToBase64(blobs.find((b) => b.name === name).blob) })));
    const { sent, failed } = await sendToTargets(list, { text, paths: sendableFiles(files), files: payloadFiles, source });
    if (!failed.length) {
      if (!useSaved) rememberChat(rememberKey, list[0]);
      onSent?.(sent.join(', '));
      onClose();
    } else {
      setState({ busy: false, error: failed.map((f) => `${f.name}: ${f.error}`).join(' · ') });
    }
  };

  return (
    <div className="modal-overlay" onClick={state.busy ? undefined : onClose}>
      <div className="swa-dialog" role="dialog" aria-modal="true" aria-labelledby="swa-dialog-title" onClick={(e) => e.stopPropagation()}>
        <h3 id="swa-dialog-title">{title || 'Send on WhatsApp'}</h3>
        <p className="swa-muted">From this store&apos;s own WhatsApp.</p>
        <ul className="swa-files">
          {sendFiles.map((f) => <li key={f} title={f}>{f.split(/[\\/]/).pop()}</li>)}
        </ul>
        {targets.length > 0 && (
          <label className="swa-check">
            <input type="checkbox" checked={useSaved} onChange={(e) => setUseSaved(e.target.checked)} />
            Saved: {targets.map((t) => t.name).join(', ')}
          </label>
        )}
        {!useSaved && (
          <label className="swa-field" htmlFor="swa-dialog-chat">
            Send to
            <ChatInput id="swa-dialog-chat" value={chat} onChange={setChat} />
          </label>
        )}
        {!useSaved && (searching
          ? <ChatPicker onPick={(c) => { setChat(c.name); setSearching(false); }} />
          : <button type="button" className="swa-link swa-link-start" onClick={() => setSearching(true)}>Search WhatsApp contacts / groups</button>)}
        <label className="swa-field" htmlFor="swa-dialog-text">
          Message (optional)
          <textarea id="swa-dialog-text" rows={2} value={text} onChange={(e) => setText(e.target.value)} />
        </label>
        {state.error && <div className="status-line error">{state.error}</div>}
        <div className="action-row">
          <button type="button" className="secondary-button" onClick={onClose} disabled={state.busy}>Cancel</button>
          <button type="button" className="primary-button" onClick={send} disabled={state.busy}>
            {state.busy ? 'Sending…' : 'Send'}
          </button>
        </div>
      </div>
    </div>
  );
}

// --- Share any report / export on WhatsApp ----------------------------------
// Report downloads call offerWhatsAppShare(); <WhatsAppShareHost/> (mounted
// once in App) shows a "Send on WhatsApp" toast for the last file. A .zip is
// opened and its files offered instead -- a zip is never sent.
const SHARE_EVENT = 'nexora:wa-share';

async function expandZipBlobs(blobs) {
  const out = [];
  for (const b of blobs) {
    if (!/\.zip$/i.test(b.name)) { out.push(b); continue; }
    const parts = unzipSync(new Uint8Array(await b.blob.arrayBuffer()));
    for (const [name, bytes] of Object.entries(parts)) {
      if (!name.endsWith('/')) out.push({ name: name.split('/').pop(), blob: new Blob([bytes]) });
    }
  }
  return out;
}

// detail: { blobs: [{ name, blob }], title?, caption?, source? }
export function offerWhatsAppShare(detail) {
  if (!storeWhatsAppAvailable()) return;
  window.dispatchEvent(new CustomEvent(SHARE_EVENT, { detail }));
}

export function WhatsAppShareHost() {
  const [offer, setOffer] = useState(null);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const onShare = async (e) => {
      const blobs = await expandZipBlobs(e.detail?.blobs || []);
      if (!blobs.length) return;
      setOffer({ ...e.detail, blobs });
      if (e.detail?.openNow) setOpen(true);
    };
    window.addEventListener(SHARE_EVENT, onShare);
    return () => window.removeEventListener(SHARE_EVENT, onShare);
  }, []);
  useEffect(() => {
    if (!offer || open) return undefined;
    const timer = setTimeout(() => setOffer(null), 20000);
    return () => clearTimeout(timer);
  }, [offer, open]);
  if (!offer) return null;
  const label = offer.blobs.length === 1 ? offer.blobs[0].name : `${offer.blobs.length} files`;
  return (
    <>
      {!open && (
        <div className="swa-share-toast" role="status">
          <span title={label}>Saved {label}</span>
          <button type="button" className="primary-button" onClick={() => setOpen(true)}>Send on WhatsApp</button>
          <button type="button" className="swa-share-x" aria-label="Dismiss" onClick={() => setOffer(null)}>×</button>
        </div>
      )}
      {open && (
        <WhatsAppSendDialog
          title={offer.title || 'Send on WhatsApp'}
          blobs={offer.blobs}
          defaultText={offer.caption || ''}
          rememberKey={offer.rememberKey || `share:${offer.source || 'report'}`}
          source={offer.source || 'Report'}
          onClose={() => { setOpen(false); setOffer(null); }}
        />
      )}
    </>
  );
}

// Explicit button: builds its files on click, then opens the send dialog.
export function WhatsAppShareButton({ label = 'WhatsApp', title, caption, source, buildFiles, disabled, className = 'secondary-button' }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  if (!storeWhatsAppAvailable()) return null;
  const click = async () => {
    setBusy(true); setError('');
    try {
      offerWhatsAppShare({ blobs: await buildFiles(), title, caption, source, openNow: true });
    } catch (e) {
      setError(e.message || 'Could not prepare the file.');
    } finally {
      setBusy(false);
    }
  };
  return (
    <button type="button" className={className} disabled={disabled || busy} onClick={click} title={error || title}>
      {busy ? 'Preparing…' : label}
    </button>
  );
}

export function StoreWhatsAppScreen({ outbox }) {
  const [engine, setEngine] = useState(whatsAppEngine);
  const [status, refresh] = useStoreWhatsAppStatus(3000, engine);
  const switchEngine = (next) => { setWhatsAppEngine(next); setEngine(next); };
  const [log, setLog] = useState([]);
  const [chat, setChat] = useState('');
  const [text, setText] = useState('');
  const [files, setFiles] = useState([]);
  const [sendState, setSendState] = useState({ busy: false, message: '', kind: '' });
  const fileInput = useRef(null);

  const loadLog = useCallback(async () => {
    try { setLog(await wa().log()); } catch { /* ignore */ }
  }, []);
  useEffect(() => { loadLog(); }, [loadLog, status.sending, engine]);

  const act = async (fn) => { await fn(); refresh(); };

  const sendFree = async () => {
    const target = chat.trim();
    if (!target) { setSendState({ busy: false, kind: 'error', message: 'Enter a chat, group or number.' }); return; }
    if (!files.length && !text.trim()) { setSendState({ busy: false, kind: 'error', message: 'Type a message or attach a file.' }); return; }
    setSendState({ busy: true, kind: 'loading', message: `Sending to ${target}…` });
    const payloadFiles = await Promise.all(files.map(async (f) => ({ name: f.name, base64: await blobToBase64(f) })));
    const result = await wa().send({ chat: target, text, files: payloadFiles, source: 'manual' });
    if (result.status === 'sent') {
      rememberChat('', target);
      setText(''); setFiles([]);
      if (fileInput.current) fileInput.current.value = '';
      setSendState({ busy: false, kind: 'ok', message: `Sent to ${target}.` });
    } else {
      setSendState({ busy: false, kind: 'error', message: result.error || 'Send failed.' });
    }
    loadLog();
  };

  const ready = status.state === 'ready';
  return (
    <section className="screen-panel swa-screen">
      <header className="screen-header">
        <div>
          <h2>WhatsApp</h2>
          <p>Orders, reports and the NMW stock file go out from this store&apos;s WhatsApp — this PC&apos;s own login, or the HO profile.</p>
        </div>
      </header>

      <div className="swa-grid">
        <div className="table-wrap swa-card">
          <h3>Send from</h3>
          <div className="swa-engine" role="radiogroup" aria-label="Which WhatsApp sends from this PC">
            <label className="swa-check">
              <input type="radio" name="swa-engine" checked={engine === 'local'} onChange={() => switchEngine('local')} />
              This PC&apos;s own WhatsApp (scan a QR here)
            </label>
            <label className="swa-check">
              <input type="radio" name="swa-engine" checked={engine === 'ho'} onChange={() => switchEngine('ho')} />
              HO WhatsApp profile{engine === 'ho' && status.profileName ? ` (${status.profileName})` : ''} — already logged in on the HO server
            </label>
          </div>
          <div className={`status-line ${ready ? 'ok' : status.state === 'qr' || status.state === 'error' ? 'error' : 'loading'}`}>
            {engine === 'ho' ? (status.error || HO_STATE_TEXT[status.state] || status.state) : STATE_TEXT[status.state] || status.state}{status.sending ? ' Sending…' : ''}
          </div>
          {engine === 'local' && status.state === 'qr' && status.qr && (
            <div className="swa-qr">
              <img src={status.qr} alt="WhatsApp login QR code" />
              <p className="swa-muted">On the store phone: WhatsApp → Settings → Linked devices → Link a device.</p>
            </div>
          )}
          {engine === 'local' && <div className="action-row">
            {status.state === 'off' && <button type="button" className="primary-button" onClick={() => act(() => wa().enable())}>Set up WhatsApp</button>}
            {status.state !== 'off' && <button type="button" className="secondary-button" onClick={() => wa().show()}>Open WhatsApp window</button>}
            {ready && <button type="button" className="secondary-button" onClick={() => { if (window.confirm('Unlink WhatsApp from this PC? You will need to scan the QR again.')) act(() => wa().unlink()); }}>Unlink</button>}
            {status.state !== 'off' && <button type="button" className="secondary-button" onClick={() => { if (window.confirm('Turn off WhatsApp on this PC? Queued stock files will not be sent from here.')) act(() => wa().disable()); }}>Turn off</button>}
          </div>}
          {outbox && (
            <p className="swa-muted">
              NMW stock file: {outbox.lastError ? `last attempt failed — ${outbox.lastError}` : outbox.lastSent ? `last sent ${outbox.lastSent}` : 'none waiting'}
            </p>
          )}
        </div>

        <div className="table-wrap swa-card">
          <h3>Send</h3>
          <label className="swa-field" htmlFor="swa-free-chat">
            To
            <ChatInput id="swa-free-chat" value={chat} onChange={setChat} />
          </label>
          <label className="swa-field" htmlFor="swa-free-text">
            Message
            <textarea id="swa-free-text" rows={3} value={text} onChange={(e) => setText(e.target.value)} />
          </label>
          <label className="swa-field" htmlFor="swa-free-files">
            Files
            <input id="swa-free-files" ref={fileInput} type="file" multiple onChange={(e) => setFiles([...e.target.files])} />
          </label>
          {sendState.message && <div className={`status-line ${sendState.kind}`}>{sendState.message}</div>}
          <div className="action-row">
            <button type="button" className="primary-button" onClick={sendFree} disabled={!ready || sendState.busy}>
              {sendState.busy ? 'Sending…' : 'Send'}
            </button>
          </div>
        </div>
      </div>

      <div className="table-wrap">
        <h3>Recent sends</h3>
        {log.length ? (
          <table>
            <thead><tr><th>Time</th><th>To</th><th>What</th><th>From</th><th>Result</th></tr></thead>
            <tbody>
              {log.slice(0, 50).map((row, i) => (
                <tr key={`${row.at}-${i}`}>
                  <td>{new Date(row.at).toLocaleString()}</td>
                  <td>{row.chat}</td>
                  <td>{[...(row.files || []), row.text].filter(Boolean).join(' · ') || '—'}</td>
                  <td>{row.source || '—'}</td>
                  <td className={row.status === 'sent' ? 'swa-ok' : 'swa-bad'} title={row.error || ''}>
                    {row.status === 'sent' ? 'Sent' : `Failed: ${row.error || ''}`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <div className="empty-state">Nothing sent from this PC yet.</div>}
      </div>
    </section>
  );
}

const OUTBOX_POLL_MS = 120000;

// Background: while WhatsApp is linked on this PC, pick up the NMW stock
// files HO queued for this store and send them to the store's group from the
// store's own number. The backend claim is atomic, so two PCs of the same
// store never both post the file.
export function useStoreWhatsAppOutbox({ session, tenantId, storeId }) {
  const [info, setInfo] = useState({ lastSent: '', lastError: '' });
  const running = useRef(false);

  useEffect(() => {
    if (!wa() || !session || !tenantId || !storeId) return undefined;
    let cancelled = false;

    const tick = async () => {
      if (running.current) return;
      running.current = true;
      try {
        const st = await wa().status();
        if (st.state !== 'ready') return;
        const { items = [] } = await api.getStoreWhatsAppOutbox(tenantId, storeId, session);
        for (const item of items) {
          if (cancelled) return;
          const chat = item.whatsapp_group || item.phone_number;
          if (!chat) continue;
          const { claimed } = await api.claimStoreWhatsAppItem(item.run_item_id, session);
          if (!claimed) continue;
          let result;
          try {
            const blob = await api.getStoreWhatsAppFile(item.run_item_id, session);
            result = await wa().send({
              chat,
              files: [{ name: item.file_name || 'NMW_Stock.xls', base64: await blobToBase64(blob) }],
              source: 'NMW stock'
            });
          } catch (err) {
            result = { status: 'failed', error: err?.message || String(err) };
          }
          await api.reportStoreWhatsAppResult(item.run_item_id, result.status === 'sent', result.error, session);
          setInfo(result.status === 'sent'
            ? { lastSent: new Date().toLocaleString(), lastError: '' }
            : { lastSent: '', lastError: result.error || 'failed' });
        }
      } catch {
        // HO unreachable / not permitted -- try again next tick.
      } finally {
        running.current = false;
      }
    };

    const first = setTimeout(tick, 15000);
    const timer = setInterval(tick, OUTBOX_POLL_MS);
    return () => { cancelled = true; clearTimeout(first); clearInterval(timer); };
  }, [session, tenantId, storeId]);

  return info;
}
