import { Fragment, forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from 'react';
import { api } from './api/client.js';
import {
  webHost, webMergeSites, webMoveSite, webUrl,
} from './webPanelView.js';

// Web panel (owner 2026-11-05): each supplier has its OWN web-order site +
// login, stored on the supplier row (OrderSuppliers.Portal*). Picking a
// supplier in Procurement and opening the Website panel loads that supplier's
// site here and signs in. A real embedded browser (<webview>: its own process,
// no access to the app); electron/webPanel.cjs locks it down. Each store (the
// Procurement store picker) has its own portal session.
//
// The panel shows:
// - the SELECTED supplier's site (from its OrderSuppliers row): its URL + login
//   are edited in "⚙ Sites"; the login is handed to the main process, which
//   keeps it encrypted on the PC so sign-in works while HO is down.
// - this PC's own sites (localStorage), with logins typed on this PC.

const SITES_KEY = 'nexora.desktop.webSites';
const LAST_KEY = 'nexora.desktop.webSiteLast';
const ZOOM_KEY = 'nexora.desktop.webZoom';
const PORTALS_PREFIX = 'nexora.desktop.webPortals::';
const ZOOMS = [0.67, 0.75, 0.8, 0.9, 1, 1.1, 1.25];

function load(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key) ?? 'null') ?? fallback; } catch { return fallback; }
}
function save(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* per-PC convenience only */ }
}
const newId = () => `s${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;

// One login (a store's, the all-stores one, or this PC's): the password is
// write-only -- blank keeps the saved one.
function LoginFields({ title, login, hint, saveLabel, doneNote, readOnly, onSave, onClear }) {
  const [username, setUsername] = useState(login?.username || '');
  const [password, setPassword] = useState('');
  const [autoSubmit, setAutoSubmit] = useState(login ? login.autoSubmit : true);
  const [note, setNote] = useState('');
  const run = (work, done) => work.then(() => { setPassword(''); setNote(done); })
    .catch((e) => setNote(e.message || 'Could not save.'));
  return (
    <div className="wp-login">
      {title && <b className="wp-login-title">{title}</b>}
      <label>Username<input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="off" disabled={readOnly} /></label>
      <label>Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password"
        disabled={readOnly} placeholder={login?.hasPassword ? 'Saved (type to change)' : ''} /></label>
      <label className="wp-check"><input type="checkbox" checked={autoSubmit} disabled={readOnly} onChange={(e) => setAutoSubmit(e.target.checked)} /> Sign in automatically</label>
      {!readOnly && (
        <div className="wp-row">
          <button type="button" className="ow-btn ow-btn-sm" disabled={!password && !login?.hasPassword}
            onClick={() => run(onSave({ username, password, autoSubmit }), doneNote)}>{saveLabel}</button>
          {login && onClear && <button type="button" className="ow-btn ow-btn-sm" onClick={() => run(onClear(), 'Login removed.')}>Remove login</button>}
        </div>
      )}
      {hint && <p className="wp-note">{hint}</p>}
      {note && <p className="wp-note">{note}</p>}
    </div>
  );
}

// The selected supplier's own web-order site: its address + login, edited
// together. Blank address clears the portal.
function SupplierPortalEditor({ store, supplierName, portal, readOnly, onSave, onClear }) {
  const [url, setUrl] = useState(portal?.url || '');
  const [username, setUsername] = useState(portal?.username || '');
  const [password, setPassword] = useState('');
  const [autoSubmit, setAutoSubmit] = useState(portal ? portal.auto_submit !== false : true);
  const [note, setNote] = useState('');
  useEffect(() => {
    setUrl(portal?.url || ''); setUsername(portal?.username || ''); setPassword('');
    setAutoSubmit(portal ? portal.auto_submit !== false : true);
  }, [portal]);
  const run = (work, done) => work.then(() => { setPassword(''); setNote(done); }).catch((e) => setNote(e.message || 'Could not save.'));
  return (
    <div className="wp-login">
      <b className="wp-login-title">{supplierName} · web order site</b>
      <label className="wp-wide">Address<input value={url} disabled={readOnly} placeholder="https://supplier.example.com"
        onChange={(e) => setUrl(e.target.value)} /></label>
      <label>Username<input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="off" disabled={readOnly} /></label>
      <label>Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password"
        disabled={readOnly} placeholder={portal?.has_password ? 'Saved (type to change)' : ''} /></label>
      <label className="wp-check"><input type="checkbox" checked={autoSubmit} disabled={readOnly} onChange={(e) => setAutoSubmit(e.target.checked)} /> Sign in automatically</label>
      {!readOnly && (
        <div className="wp-row">
          <button type="button" className="ow-btn ow-btn-sm" disabled={!url.trim()}
            onClick={() => run(onSave({ url, username, password, auto_submit: autoSubmit }), 'Saved — picking this supplier opens its site.')}>Save site</button>
          {portal?.url && <button type="button" className="ow-btn ow-btn-sm" onClick={() => run(onClear(), 'Site removed.')}>Remove site</button>}
        </div>
      )}
      {note && <p className="wp-note">{note}</p>}
    </div>
  );
}

// Remount per store (key={store}): another store = another portal session.
// The ref drives the open site for the Website check (siteCheckBar.jsx).
// The supplier's display name from the store's supplier list.
function supplierName(suppliers, code) {
  const s = (Array.isArray(suppliers) ? suppliers : []).find((x) => String(x.supplier_code) === String(code));
  return s ? String(s.supplier_name || '').trim() : '';
}

const WebPanel = forwardRef(function WebPanel({ store = '', session = null, suppliers = [], supplierCode = '', onPortal }, ref) {
  const desk = typeof window !== 'undefined' ? window.nexoraDesktop?.web : null;
  const [sites, setSites] = useState(() => { const s = load(SITES_KEY, []); return Array.isArray(s) ? s : []; });
  // The selected supplier's own web-order portal (from its OrderSuppliers row).
  const [supPortal, setSupPortal] = useState(() => ({ portal: store && supplierCode ? load(`${PORTALS_PREFIX}${store}::${supplierCode}`, null) : null, canEdit: false, offline: false }));
  // The selected supplier's site sits at the front of the bar when set.
  const portalSites = supPortal.portal?.url
    ? [{ id: `sup:${supplierCode}`, name: supplierName(suppliers, supplierCode) || webHost(supPortal.portal.url), url: supPortal.portal.url, portal: supPortal.portal }]
    : [];
  const bar = [...portalSites, ...sites];
  const [activeId, setActiveId] = useState(() => load(LAST_KEY, ''));
  const active = bar.find((s) => s.id === activeId) || bar[0] || null;
  // The <webview> mounts on the first site; later moves use loadURL.
  const [startUrl, setStartUrl] = useState(() => active?.url || '');
  const [address, setAddress] = useState(() => active?.url || '');
  const [nav, setNav] = useState({ back: false, forward: false, loading: false, url: '', error: '' });
  const [zoom, setZoom] = useState(() => { const z = Number(load(ZOOM_KEY, 0.9)); return ZOOMS.includes(z) ? z : 0.9; });
  const [manageOpen, setManageOpen] = useState(false);
  const [openFor, setOpenFor] = useState('');   // '<site id>:login'
  const [logins, setLogins] = useState({});
  const [draft, setDraft] = useState({ name: '', url: '' });
  const [note, setNote] = useState('');
  const viewRef = useRef(null);
  const readyRef = useRef(false);
  const editingRef = useRef(false);
  const zoomRef = useRef(zoom);
  const lastSupplierRef = useRef('');
  useImperativeHandle(ref, () => ({
    ready: () => Boolean(readyRef.current && viewRef.current),
    loading: () => (viewRef.current ? viewRef.current.isLoading() : true),
    url: () => { try { return viewRef.current ? viewRef.current.getURL() : ''; } catch { return ''; } },
    exec: (code) => (readyRef.current && viewRef.current ? viewRef.current.executeJavaScript(code) : Promise.reject(new Error('The site is not open yet.'))),
    openUrl: (u) => open(u),   // drive the view to a supplier's site (Auto Assign stock check)
  }), []);

  useEffect(() => { save(SITES_KEY, sites); }, [sites]);
  useEffect(() => { if (active) save(LAST_KEY, active.id); }, [active]);
  useEffect(() => {
    zoomRef.current = zoom;
    save(ZOOM_KEY, zoom);
    if (readyRef.current) viewRef.current?.setZoomFactor(zoom);
  }, [zoom]);
  useEffect(() => { desk?.logins(store).then(setLogins).catch(() => {}); }, [desk, store]);

  // The selected supplier's portal (URL + whether a login's set), then its
  // login into the PC's encrypted cache for auto sign-in. HO down: keep the
  // last cached portal + login.
  const refreshPortal = useCallback((fresh = false) => {
    if (!store || !supplierCode || !session) { setSupPortal({ portal: null, canEdit: false, offline: false }); return Promise.resolve(); }
    return api.legacySupplierPortal(store, supplierCode, session).then((r) => {
      const portal = r?.portal || null;
      save(`${PORTALS_PREFIX}${store}::${supplierCode}`, portal);
      setSupPortal({ portal, canEdit: Boolean(r?.can_edit), offline: false });
      onPortal?.(portal);
      if (!desk || !portal?.url) return null;
      if (!r?.can_edit) return desk.syncLogins(store, [], fresh);
      return api.legacySupplierPortalLogin(store, supplierCode, session)
        .then((res) => { const l = res?.login; return desk.syncLogins(store, l ? [{ url: l.url, username: l.username, password: l.password, autoSubmit: l.auto_submit }] : [], fresh); })
        .catch(() => null);
    }).catch(() => setSupPortal((cur) => ({ ...cur, offline: true })));
  }, [desk, store, supplierCode, session]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { refreshPortal(); }, [refreshPortal]);

  useEffect(() => {
    const view = viewRef.current;
    if (!view) return undefined;
    readyRef.current = false;
    const sync = () => {
      if (!readyRef.current) return;
      const url = view.getURL();
      setNav({ back: view.canGoBack(), forward: view.canGoForward(), loading: view.isLoading(), url, error: '' });
      if (!editingRef.current) setAddress(url);
    };
    const onReady = () => { readyRef.current = true; view.setZoomFactor(zoomRef.current); sync(); };
    // -3 = aborted (a redirect or a newer navigation), not a failure.
    const onFail = (e) => {
      if (e.isMainFrame && e.errorCode !== -3) setNav((n) => ({ ...n, loading: false, error: e.errorDescription || 'Could not open the page.' }));
    };
    const events = ['did-navigate', 'did-navigate-in-page', 'did-start-loading', 'did-stop-loading'];
    view.addEventListener('dom-ready', onReady);
    events.forEach((name) => view.addEventListener(name, sync));
    view.addEventListener('did-fail-load', onFail);
    return () => {
      view.removeEventListener('dom-ready', onReady);
      events.forEach((name) => view.removeEventListener(name, sync));
      view.removeEventListener('did-fail-load', onFail);
    };
  }, [startUrl]);

  // Picking a supplier in Procurement opens that supplier's own site.
  useEffect(() => {
    const url = supPortal.portal?.url;
    if (!supplierCode || !url) { lastSupplierRef.current = supplierCode; return; }
    if (supplierCode === lastSupplierRef.current) return;
    lastSupplierRef.current = supplierCode;
    openSite({ id: `sup:${supplierCode}`, url });
  }, [supplierCode, supPortal.portal]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!desk) return <div className="wp-empty">The Web panel works in the desktop app.</div>;

  function open(text) {
    const url = webUrl(text);
    if (!url) return;
    editingRef.current = false;
    setAddress(url);
    if (viewRef.current && readyRef.current) viewRef.current.loadURL(url).catch(() => {});
    else setStartUrl(url);
  }
  function openSite(site) {
    setActiveId(site.id);
    open(site.url);
  }
  function addSites(incoming) {
    const next = webMergeSites(sites, incoming, newId);
    setSites(next);
    if (!active && next.length) openSite(next[0]);
    return next.length - sites.length;
  }
  function importChrome() {
    desk.chromeBookmarks()
      .then((found) => {
        const added = addSites(found);
        setNote(found.length ? `Added ${added} site${added === 1 ? '' : 's'} from Chrome (${found.length - added} already here).` : 'No Chrome bookmarks found on this PC.');
      })
      .catch((e) => setNote(e.message || 'Could not read Chrome bookmarks.'));
  }
  function removeSite(site) {
    setSites((cur) => cur.filter((s) => s.id !== site.id));
  }
  const toggle = (key) => setOpenFor((cur) => (cur === key ? '' : key));
  // Save / clear the selected supplier's portal, then refresh.
  function saveSupplierPortal(payload) {
    return api.legacySaveSupplierPortal(store, supplierCode, payload, session).then(() => refreshPortal(true));
  }
  function clearSupplierPortal() {
    return api.legacySaveSupplierPortal(store, supplierCode, { clear: true }, session).then(() => refreshPortal(true));
  }
  const step = (dir) => setZoom((z) => ZOOMS[Math.min(ZOOMS.length - 1, Math.max(0, ZOOMS.indexOf(z) + dir))]);
  const call = (fn) => { if (readyRef.current) fn(viewRef.current); };

  return (
    <section className="wp" aria-label="Supplier websites">
      <div className="wp-sites" role="tablist">
        {bar.map((s, i) => (
          <Fragment key={s.id}>
            {i === portalSites.length && i > 0 && <span className="wp-sites-gap" aria-hidden="true" />}
            <button type="button" role="tab" aria-selected={active?.id === s.id}
              title={s.url}
              className={`wp-site${active?.id === s.id ? ' is-active' : ''}${(s.portal ? s.portal.has_password : logins[webHost(s.url)]?.hasPassword) ? ' has-login' : ''}`}
              onClick={() => openSite(s)}>{s.name}</button>
          </Fragment>
        ))}
        <button type="button" className="wp-site wp-site--manage" aria-expanded={manageOpen} onClick={() => setManageOpen((v) => !v)}>⚙ Sites</button>
      </div>
      <div className="wp-bar">
        <button type="button" className="wp-btn" aria-label="Back" disabled={!nav.back} onClick={() => call((v) => v.goBack())}>◀</button>
        <button type="button" className="wp-btn" aria-label="Forward" disabled={!nav.forward} onClick={() => call((v) => v.goForward())}>▶</button>
        <button type="button" className="wp-btn" aria-label={nav.loading ? 'Stop' : 'Reload'} onClick={() => call((v) => (nav.loading ? v.stop() : v.reload()))}>{nav.loading ? '✕' : '⟳'}</button>
        <button type="button" className="wp-btn" aria-label="Site home" disabled={!active} onClick={() => active && open(active.url)}>⌂</button>
        <input className="wp-address" value={address} spellCheck={false} aria-label="Address"
          placeholder="Type a web address and press Enter"
          onFocus={(e) => { editingRef.current = true; e.target.select(); }}
          onBlur={() => { editingRef.current = false; }}
          onChange={(e) => setAddress(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') { e.preventDefault(); open(address); e.currentTarget.blur(); }
            else if (e.key === 'Escape') { setAddress(nav.url); e.currentTarget.blur(); }
          }} />
        <button type="button" className="wp-btn" aria-label="Zoom out" disabled={zoom === ZOOMS[0]} onClick={() => step(-1)}>−</button>
        <span className="wp-zoom">{Math.round(zoom * 100)}%</span>
        <button type="button" className="wp-btn" aria-label="Zoom in" disabled={zoom === ZOOMS[ZOOMS.length - 1]} onClick={() => step(1)}>+</button>
        <button type="button" className="wp-btn" aria-label="Open in browser" title="Open in your normal browser"
          disabled={!(nav.url || active)} onClick={() => desk.openExternal(nav.url || active.url)}>↗</button>
      </div>
      {nav.error && <div className="wp-error" role="alert">{nav.error}</div>}

      <div className="wp-view">
        {startUrl ? (
          <webview ref={viewRef} src={startUrl} partition={desk.partitionFor(store)} allowpopups="true" className="wp-webview" />
        ) : (
          <div className="wp-empty">
            <p>Add your supplier portals here — they open beside the order grid.</p>
            <div className="wp-row">
              <button type="button" className="ow-btn ow-btn-sm" onClick={importChrome}>Import Chrome bookmarks</button>
              <button type="button" className="ow-btn ow-btn-sm" onClick={() => setManageOpen(true)}>+ Add site</button>
            </div>
            {note && <p className="wp-note">{note}</p>}
          </div>
        )}

        {manageOpen && (
          <div className="wp-manage" role="dialog" aria-label="Supplier sites">
            <div className="wp-manage-head">
              <b>Supplier web order site{store ? ` · ${store}` : ''}</b>
              <button type="button" className="wp-btn" aria-label="Close" onClick={() => setManageOpen(false)}>✕</button>
            </div>
            {note && <p className="wp-note">{note}</p>}
            {!store && <p className="wp-note">Pick a store first.</p>}
            {store && !supplierCode && <p className="wp-note">Select a supplier in the order to set its web order site + login.</p>}
            {store && supplierCode && supPortal.offline && <p className="wp-note">HO is not reachable — showing the last saved site; sign-in still works. Changes wait for HO.</p>}
            {store && supplierCode && (
              <SupplierPortalEditor key={`${store}:${supplierCode}`} store={store}
                supplierName={supplierName(suppliers, supplierCode) || supplierCode}
                portal={supPortal.portal} readOnly={supPortal.offline || !supPortal.canEdit}
                onSave={saveSupplierPortal} onClear={clearSupplierPortal} />
            )}

            <div className="wp-manage-head wp-manage-sub">
              <b>This PC’s sites</b>
              <button type="button" className="ow-btn ow-btn-sm" onClick={importChrome}>Import Chrome bookmarks</button>
            </div>
            <form className="wp-row wp-add" onSubmit={(e) => {
              e.preventDefault();
              if (!webUrl(draft.url)) return;
              const added = addSites([draft]);
              setNote(added ? '' : 'That site is already in the list.');
              setDraft({ name: '', url: '' });
            }}>
              <input placeholder="Name" value={draft.name} onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))} />
              <input placeholder="Address" value={draft.url} onChange={(e) => setDraft((d) => ({ ...d, url: e.target.value }))} />
              <button type="submit" className="ow-btn ow-btn-sm" disabled={!draft.url.trim()}>+ Add</button>
            </form>
            <ul className="wp-list">
              {sites.map((s) => {
                const login = logins[webHost(s.url)];
                return (
                  <li key={s.id}>
                    <div className="wp-row">
                      <span className="wp-list-name" title={s.url}>{s.name}<small>{webHost(s.url)}</small></span>
                      <button type="button" className={`ow-btn ow-btn-sm${login?.hasPassword ? ' wp-has-login' : ''}`}
                        aria-expanded={openFor === `${s.id}:login`} onClick={() => toggle(`${s.id}:login`)}>
                        {login?.hasPassword ? (login.fromPc ? '🔑 PC login' : '🔑 Login saved') : 'Login…'}
                      </button>
                      <button type="button" className="wp-btn" aria-label={`Move ${s.name} up`} onClick={() => setSites((cur) => webMoveSite(cur, s.id, -1))}>▲</button>
                      <button type="button" className="wp-btn" aria-label={`Move ${s.name} down`} onClick={() => setSites((cur) => webMoveSite(cur, s.id, 1))}>▼</button>
                      <button type="button" className="wp-btn" aria-label={`Remove ${s.name}`} onClick={() => removeSite(s)}>✕</button>
                    </div>
                    {openFor === `${s.id}:login` && (
                      <LoginFields key={s.id} login={login && !login.fromPc ? login : null}
                        saveLabel={`Save login for ${store || 'this PC'}`}
                        doneNote={`Saved for ${store || 'this PC'} on ${webHost(s.url)} (encrypted on this PC).`}
                        hint={login?.fromPc ? `Using this PC’s login. Save one here to give ${store} its own.` : ''}
                        onSave={(x) => desk.saveLogin({ store, url: s.url, ...x }).then(setLogins)}
                        onClear={() => desk.clearLogin(store, s.url).then(setLogins)} />
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </div>
    </section>
  );
});

export default WebPanel;
