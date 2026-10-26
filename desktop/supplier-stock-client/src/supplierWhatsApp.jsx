// Supplier-wise WhatsApp for the Procurement workspace.
//   - SupplierWhatsAppDialog: pick the supplier's WhatsApp target -- ONE group,
//     or one or more contacts -- searched from this PC's WhatsApp, plus the
//     auto-send rule (batch size, image / Excel / both, bills+CN days).
//   - useSupplierWhatsApp: the engine. After every assignment it checks the
//     supplier's unsent assigned products; at the batch size it exports just
//     those (org + supplier title on every image, bills/CN under the last one)
//     and posts them from the store's own WhatsApp. At finalize it sends each
//     auto-send supplier the COMPLETE order. Sent products are logged on the
//     server (OrderNMC dbo.SupplierWhatsAppSent), so no batch repeats a line.
import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from './api/client.js';
import { ChatPicker, sendToTargets, sendableFiles, storeWhatsAppAvailable } from './storeWhatsApp.jsx';

const EXCEL_HEADER_KEY = 'nexora.desktop.waExcelHeader';
const readExcelHeader = () => { try { return localStorage.getItem(EXCEL_HEADER_KEY) === '1'; } catch { return false; } };

const FORMATS = [['image', 'Images'], ['excel', 'Excel'], ['both', 'Images + Excel']];

// One group wins alone; otherwise any number of contacts (server rule too).
function addTarget(list, chat) {
  if (chat.kind === 'group') return [chat];
  return [...list.filter((t) => t.kind !== 'group' && t.name.toLowerCase() !== chat.name.toLowerCase()), chat];
}

export function SupplierWhatsAppDialog({ store, supplier, contact, session, onClose, onSaved }) {
  const [targets, setTargets] = useState(contact?.targets || []);
  const [autoSend, setAutoSend] = useState(Boolean(contact?.auto_send));
  const [batchSize, setBatchSize] = useState(contact?.batch_size || 20);
  const [format, setFormat] = useState(contact?.send_format || 'image');
  const [billDays, setBillDays] = useState(contact?.bill_days ?? 2);
  const [excelHeader, setExcelHeader] = useState(readExcelHeader);
  const [manual, setManual] = useState({ name: '', kind: 'contact' });
  const [state, setState] = useState({ busy: false, error: '' });
  const canSearch = storeWhatsAppAvailable();

  const save = async (nextTargets = targets) => {
    setState({ busy: true, error: '' });
    try {
      try { localStorage.setItem(EXCEL_HEADER_KEY, excelHeader ? '1' : '0'); } catch { /* per-PC preference */ }
      const res = await api.legacySaveWhatsAppContact(store, {
        supplier_code: supplier.supplier_code, supplier_name: supplier.supplier_name, targets: nextTargets,
        auto_send: autoSend, batch_size: Number(batchSize) || 20, send_format: format, bill_days: Number(billDays) || 0,
      }, session);
      onSaved?.(res.item);
      onClose();
    } catch (e) {
      setState({ busy: false, error: e.message || 'Save failed.' });
    }
  };
  const addManual = () => {
    const name = manual.name.trim();
    if (!name) return;
    setTargets((cur) => addTarget(cur, { name, kind: manual.kind }));
    setManual({ name: '', kind: manual.kind });
  };

  return (
    <div className="modal-overlay" onClick={state.busy ? undefined : onClose}>
      <div className="swa-dialog swa-dialog-wide" role="dialog" aria-modal="true" aria-labelledby="swa-sup-title" onClick={(e) => e.stopPropagation()}>
        <h3 id="swa-sup-title">WhatsApp — {supplier.supplier_name}</h3>
        <p className="swa-muted">Orders for this supplier go to one group, or to one or more contacts.</p>

        <div className="swa-targets" aria-label="Saved WhatsApp targets">
          {targets.length ? targets.map((t) => (
            <span key={t.name} className={`swa-chip swa-kind-${t.kind}`}>
              {t.kind === 'group' ? 'Group' : 'Contact'} · {t.name}
              <button type="button" aria-label={`Remove ${t.name}`} onClick={() => setTargets((cur) => cur.filter((x) => x.name !== t.name))}>×</button>
            </span>
          )) : <span className="swa-muted">No WhatsApp target yet.</span>}
        </div>

        {canSearch
          ? <ChatPicker picked={targets} onPick={(chat) => setTargets((cur) => addTarget(cur, chat))} />
          : <p className="swa-muted">Set up WhatsApp on this PC (WhatsApp screen) to search contacts and groups.</p>}
        <div className="swa-picker-bar">
          <input value={manual.name} onChange={(e) => setManual({ ...manual, name: e.target.value })}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addManual(); } }}
            placeholder="Or type an exact chat name / phone number" aria-label="Chat name or phone number" />
          <select value={manual.kind} onChange={(e) => setManual({ ...manual, kind: e.target.value })} aria-label="Chat type">
            <option value="contact">Contact</option>
            <option value="group">Group</option>
          </select>
          <button type="button" className="secondary-button" onClick={addManual}>Add</button>
        </div>

        <fieldset className="swa-rule">
          <legend>Auto send</legend>
          <label className="swa-check">
            <input type="checkbox" checked={autoSend} onChange={(e) => setAutoSend(e.target.checked)} />
            Send automatically while assigning
          </label>
          <div className="swa-rule-grid">
            <label className="swa-field">Send every
              <span className="swa-inline"><input type="number" min="1" max="500" value={batchSize} onChange={(e) => setBatchSize(e.target.value)} disabled={!autoSend} /> products</span>
            </label>
            <label className="swa-field">Send as
              <select value={format} onChange={(e) => setFormat(e.target.value)}>
                {FORMATS.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
              </select>
            </label>
            <label className="swa-field">Bills + CN at the end
              <select value={billDays} onChange={(e) => setBillDays(e.target.value)}>
                <option value="0">Off</option>
                {[1, 2, 3, 5, 7].map((d) => <option key={d} value={d}>{d === 1 ? 'Today' : `Last ${d} days`}</option>)}
              </select>
            </label>
          </div>
          <p className="swa-muted">The complete order is also sent to this supplier when the order is finalized.</p>
          <label className="swa-check">
            <input type="checkbox" checked={excelHeader} onChange={(e) => setExcelHeader(e.target.checked)} />
            Add organisation / supplier title rows to Excel files (all suppliers, this PC)
          </label>
        </fieldset>

        {state.error && <div className="status-line error">{state.error}</div>}
        <div className="action-row">
          {contact && <button type="button" className="secondary-button" onClick={() => save([])} disabled={state.busy}>Remove</button>}
          <button type="button" className="secondary-button" onClick={onClose} disabled={state.busy}>Cancel</button>
          <button type="button" className="primary-button" onClick={() => save()} disabled={state.busy || !targets.length}>
            {state.busy ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}

// columnsFor(): the export column keys the workspace uses (null = legacy fixed).
export function useSupplierWhatsApp({ store, session, exportKit, exportSettings, columnsFor, orderNo, onBanner, onError }) {
  const [contacts, setContacts] = useState({});
  const queue = useRef(Promise.resolve());
  const [busy, setBusy] = useState('');
  const latest = useRef({});
  latest.current = { exportSettings, columnsFor, orderNo, onBanner, onError };

  const reload = useCallback(() => {
    if (!store) { setContacts({}); return; }
    api.legacyWhatsAppContacts(store, session)
      .then((res) => setContacts(Object.fromEntries((res.items || []).map((c) => [String(c.supplier_code), c]))))
      .catch(() => setContacts({}));
  }, [store, session]);
  useEffect(() => { reload(); }, [reload]);

  const sendOrder = useCallback(async (supplierCode, kind) => {
    const contact = contacts[String(supplierCode)];
    if (!contact?.targets?.length || !storeWhatsAppAvailable()) return;
    const { exportSettings: settings, columnsFor: cols, orderNo: order, onBanner: banner } = latest.current;
    const st = await api.legacyWhatsAppStatus(store, supplierCode, session);
    if (kind === 'batch' && st.unsent_codes.length < contact.batch_size) return;
    if (kind === 'final' && !st.assigned_count) return;
    const name = contact.supplier_name || String(supplierCode);
    const suffix = kind === 'final' ? 'Complete' : `Batch ${st.batches_sent + 1}`;
    setBusy(`Sending ${name} ${suffix.toLowerCase()} on WhatsApp…`);
    const dateFolder = exportKit.dateFolder();
    const orderPart = order || dateFolder;
    const { blob, filename, exportedCount } = await api.legacyExportOrder(store, supplierCode, name, 'history', 0, session, {
      columns: cols ? cols() : undefined,
      fileFormat: settings.fileFormat,
      orderNo: orderPart,
      onlyCodes: kind === 'batch' ? st.unsent_codes : undefined,
      images: contact.send_format !== 'excel',
      imageHeader: true,
      excelHeader: readExcelHeader(),
      billsDays: contact.bill_days,
      nameSuffix: suffix,
    });
    const written = [];
    const folder = [settings.basePath, 'Export', dateFolder, exportKit.safePathSegment(orderPart), 'WhatsApp', exportKit.safePathSegment(name)].join('\\');
    const ext = ['csv', 'xlsx'].includes(settings.fileFormat) ? settings.fileFormat : 'xls';
    await exportKit.save(blob, filename, `${exportKit.safeFileName(`${name} ${store} ${suffix}`)}.${ext}`, folder, written);
    const isImage = (p) => /\.png$/i.test(p);
    const files = sendableFiles(written.filter((p) => (contact.send_format === 'image' ? isImage(p)
      : contact.send_format === 'excel' ? !isImage(p) : true)));
    if (!files.length) throw new Error(`Nothing to send for ${name}.`);
    const caption = kind === 'final'
      ? `Complete order — ${exportedCount} product${exportedCount === 1 ? '' : 's'}. Please confirm availability.`
      : `Order ${suffix} — ${exportedCount} product${exportedCount === 1 ? '' : 's'}.`;
    const { sent, failed } = await sendToTargets(contact.targets, { text: caption, paths: files, source: `Order ${suffix}` });
    if (sent.length) {
      await api.legacyMarkWhatsAppSent(store, supplierCode, kind === 'batch' ? st.unsent_codes : ['*'], kind, session);
    }
    if (failed.length) throw new Error(`WhatsApp to ${failed.map((f) => `${f.name} (${f.error})`).join(', ')} failed.`);
    banner?.(`Sent ${name} ${suffix.toLowerCase()} (${exportedCount} products) on WhatsApp to ${sent.join(', ')}.`);
  }, [contacts, store, session, exportKit]);

  const enqueue = useCallback((supplierCode, kind) => {
    queue.current = queue.current
      .then(() => sendOrder(supplierCode, kind))
      .catch((e) => latest.current.onError?.(e.message || 'WhatsApp send failed.'))
      .finally(() => setBusy(''));
    return queue.current;
  }, [sendOrder]);

  // After an assignment: batch-send if this supplier is on auto-send.
  const onAssigned = useCallback((supplierCode) => {
    if (contacts[String(supplierCode)]?.auto_send) enqueue(supplierCode, 'batch');
  }, [contacts, enqueue]);

  // At finalize: the complete order to every auto-send supplier.
  const sendFinalAll = useCallback(() => {
    Object.values(contacts).filter((c) => c.auto_send).forEach((c) => enqueue(c.supplier_code, 'final'));
  }, [contacts, enqueue]);

  return { contacts, reload, busy, onAssigned, sendFinalAll, sendNow: enqueue };
}
