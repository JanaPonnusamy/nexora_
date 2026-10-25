// Store-level WhatsApp (renderer side). The WhatsApp Web session itself lives
// in the Electron main process (electron/whatsapp.cjs) on THIS store PC; this
// file is the UI around it:
//   - StoreWhatsAppScreen: link (QR) / unlink, send anything to any chat, log.
//   - WhatsAppSendDialog: "Send on WhatsApp" for an exported order file.
//   - useStoreWhatsAppOutbox: sends the NMW stock files HO queued for this
//     store (distribution whatsapp_sender = STORE) from the store's number.
import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from './api/client.js';

const wa = () => window.nexoraDesktop?.whatsapp;
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
  ready: 'Linked and ready to send.'
};

export function useStoreWhatsAppStatus(pollMs = 3000) {
  const [status, setStatus] = useState({ state: 'off' });
  const refresh = useCallback(async () => {
    if (!wa()) return;
    try { setStatus(await wa().status()); } catch { /* main process busy */ }
  }, []);
  useEffect(() => {
    if (!wa()) return undefined;
    refresh();
    const timer = setInterval(refresh, pollMs);
    return () => clearInterval(timer);
  }, [refresh, pollMs]);
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

// "Send on WhatsApp" for already-saved files (an order export). Remembers the
// chat per rememberKey (e.g. the supplier code) for next time.
export function WhatsAppSendDialog({ title, files, rememberKey, defaultChat = '', source, onClose, onSent }) {
  const [chat, setChat] = useState(() => rememberedChat(rememberKey) || defaultChat);
  const [text, setText] = useState('');
  const [state, setState] = useState({ busy: false, error: '' });

  const send = async () => {
    const target = chat.trim();
    if (!target) { setState({ busy: false, error: 'Enter the WhatsApp chat, group or number.' }); return; }
    setState({ busy: true, error: '' });
    const result = await wa().send({ chat: target, text, paths: files, source });
    if (result.status === 'sent') {
      rememberChat(rememberKey, target);
      onSent?.(target);
      onClose();
    } else {
      setState({ busy: false, error: result.error || 'Send failed.' });
    }
  };

  return (
    <div className="modal-overlay" onClick={state.busy ? undefined : onClose}>
      <div className="swa-dialog" role="dialog" aria-modal="true" aria-labelledby="swa-dialog-title" onClick={(e) => e.stopPropagation()}>
        <h3 id="swa-dialog-title">{title || 'Send on WhatsApp'}</h3>
        <p className="swa-muted">From this store&apos;s own WhatsApp.</p>
        <ul className="swa-files">
          {files.map((f) => <li key={f} title={f}>{f.split(/[\\/]/).pop()}</li>)}
        </ul>
        <label className="swa-field" htmlFor="swa-dialog-chat">
          Send to
          <ChatInput id="swa-dialog-chat" value={chat} onChange={setChat} />
        </label>
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

export function StoreWhatsAppScreen({ outbox }) {
  const [status, refresh] = useStoreWhatsAppStatus(3000);
  const [log, setLog] = useState([]);
  const [chat, setChat] = useState('');
  const [text, setText] = useState('');
  const [files, setFiles] = useState([]);
  const [sendState, setSendState] = useState({ busy: false, message: '', kind: '' });
  const fileInput = useRef(null);

  const loadLog = useCallback(async () => {
    try { setLog(await wa().log()); } catch { /* ignore */ }
  }, []);
  useEffect(() => { loadLog(); }, [loadLog, status.sending]);

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
          <p>This store&apos;s own WhatsApp — orders, pending lists and the NMW stock file go out from the store&apos;s number.</p>
        </div>
      </header>

      <div className="swa-grid">
        <div className="table-wrap swa-card">
          <h3>Link</h3>
          <div className={`status-line ${ready ? 'ok' : status.state === 'qr' ? 'error' : 'loading'}`}>
            {STATE_TEXT[status.state] || status.state}{status.sending ? ' Sending…' : ''}
          </div>
          {status.state === 'qr' && status.qr && (
            <div className="swa-qr">
              <img src={status.qr} alt="WhatsApp login QR code" />
              <p className="swa-muted">On the store phone: WhatsApp → Settings → Linked devices → Link a device.</p>
            </div>
          )}
          <div className="action-row">
            {status.state === 'off' && <button type="button" className="primary-button" onClick={() => act(() => wa().enable())}>Set up WhatsApp</button>}
            {status.state !== 'off' && <button type="button" className="secondary-button" onClick={() => wa().show()}>Open WhatsApp window</button>}
            {ready && <button type="button" className="secondary-button" onClick={() => { if (window.confirm('Unlink WhatsApp from this PC? You will need to scan the QR again.')) act(() => wa().unlink()); }}>Unlink</button>}
            {status.state !== 'off' && <button type="button" className="secondary-button" onClick={() => { if (window.confirm('Turn off WhatsApp on this PC? Queued stock files will not be sent from here.')) act(() => wa().disable()); }}>Turn off</button>}
          </div>
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
