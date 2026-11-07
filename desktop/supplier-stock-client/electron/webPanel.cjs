// Web panel (Procurement): the supplier ordering portals inside the Stock
// Client, beside the order grid (owner 2026-11-04 -- the Chrome bookmarks bar
// on the store PCs: Aosta BackBone, VarthagamSoft, RetailOrders...).
//
// The page side is a <webview> (src/webPanel.jsx). Everything that makes it
// safe lives here, in the main process:
// - every <webview> the app attaches is locked down: no preload, no Node,
//   sandboxed, http(s) only, and always a 'persist:web-panel-<store>'
//   session -- one per store, because each store has its own account on a
//   portal (an NMS sign-in must never carry over to NMW). Sign-ins survive
//   restarts but share nothing with the app;
// - saved portal logins (per store + site) are encrypted with safeStorage
//   (Windows DPAPI: only this Windows user on this PC can read them) and
//   never go back to the page. On a page of the login's own host the main
//   process fills the form, and presses its Login/Submit button at most once
//   a minute per site, so a wrong password can't loop or lock the account;
// - logins kept at HO (the store's supplier portals, dbo.SupplierPortal*)
//   arrive from the page after each fetch and are cached the same way, in
//   their own file, so the portals still sign in while HO is down. They win
//   over a login typed on this PC for the same store and site.
const fs = require('node:fs');
const path = require('node:path');
const { app, ipcMain, safeStorage, session, shell } = require('electron');

const PARTITION = 'persist:web-panel';
const PARTITION_RE = /^persist:web-panel(-[a-z0-9_-]{1,40})?$/;
// Store code <-> its session: 'NMS' <-> 'persist:web-panel-nms'.
const storeKey = (store) => String(store || '').trim().toUpperCase();
const partitionFor = (store) => (storeKey(store) ? `${PARTITION}-${storeKey(store).toLowerCase().replace(/[^a-z0-9_-]/g, '_')}` : PARTITION);
const loginKey = (store, host) => `${storeKey(store)}|${host}`;
// Same reason as whatsapp.cjs: Electron 22's own UA (Electron + Chrome 108)
// gets "unsupported browser" pages on some portals.
const USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36';
const SUBMIT_GAP_MS = 60000;
const lastSubmit = new Map();

const loginsFile = () => path.join(app.getPath('userData'), 'web-panel-logins.json');
const hoLoginsFile = () => path.join(app.getPath('userData'), 'web-panel-ho-logins.json');
const hostOf = (url) => { try { return new URL(url).host.toLowerCase(); } catch { return ''; } };
const isWeb = (url) => /^https?:\/\//i.test(String(url || ''));

function readLogins(file = loginsFile()) {
  try {
    const map = JSON.parse(fs.readFileSync(file, 'utf8'));
    return map && typeof map === 'object' ? map : {};
  } catch {
    return {};
  }
}
function writeLogins(map, file = loginsFile()) {
  fs.writeFileSync(file, JSON.stringify(map, null, 2));
}
// A login saved with no store picked is this PC's login: the fallback for
// every store that has none of its own (e.g. saved while HO was down and
// the store list could not load).
function findLogin(map, store, host) {
  return map[loginKey(store, host)] || map[loginKey('', host)] || null;
}

// What the page may know, for one store: who, and whether a password is
// saved -- never the password. Keyed by host; fromPc = the PC fallback.
function publicLogins(store) {
  const map = readLogins();
  const hosts = new Set(Object.keys(map).map((key) => key.slice(key.indexOf('|') + 1)));
  const out = {};
  for (const host of hosts) {
    const own = map[loginKey(store, host)];
    const l = findLogin(map, store, host);
    if (l) out[host] = { username: l.username || '', hasPassword: Boolean(l.password), autoSubmit: Boolean(l.autoSubmit), fromPc: !own && Boolean(storeKey(store)) };
  }
  return out;
}

// Runs inside the portal page. Fills the one visible password box and the
// text box just before it (the username), with the input/change events
// Angular/React/WebForms pages listen for, then optionally presses the
// nearest Login / Sign in / Submit button. Pages with two or more visible
// password boxes (change-password forms) are left alone.
function fillLogin(username, password, submit) {
  return new Promise((resolve) => {
    const visible = (el) => el.getClientRects().length > 0 && !el.disabled && getComputedStyle(el).visibility !== 'hidden';
    const isText = (el) => /^(text|email|tel|number|search|)$/i.test(el.getAttribute('type') || '');
    const isLogin = (el) => /^(log ?in|sign ?in|submit|login now)$/i.test(String(el.innerText || el.value || '').trim());
    const setValue = (el, value) => {
      el.focus();
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(el, value);
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
    };
    let tries = 0;
    const attempt = () => {
      const boxes = [...document.querySelectorAll('input[type=password]')].filter(visible);
      if (boxes.length !== 1) {
        // Single-page apps draw the form after load: look again for ~6s.
        if (!boxes.length && (tries += 1) < 24) setTimeout(attempt, 250);
        else resolve(boxes.length ? 'skipped' : 'no-form');
        return;
      }
      const pw = boxes[0];
      const before = [...document.querySelectorAll('input')]
        .filter((el) => visible(el) && isText(el) && (el.compareDocumentPosition(pw) & Node.DOCUMENT_POSITION_FOLLOWING));
      const user = before[before.length - 1];
      if (user && username) setValue(user, username);
      setValue(pw, password);
      if (!submit) { resolve('filled'); return; }
      let button = null;
      for (let node = pw.parentElement; node && !button; node = node.parentElement) {
        button = [...node.querySelectorAll('button, input[type=submit], input[type=button], a')].find((el) => visible(el) && isLogin(el)) || null;
      }
      setTimeout(() => {
        if (button) button.click();
        else if (pw.form) { if (pw.form.requestSubmit) pw.form.requestSubmit(); else pw.form.submit(); }
        resolve(button || pw.form ? 'submitted' : 'filled');
      }, 400);
    };
    attempt();
  });
}

function autoLogin(contents, store) {
  const host = hostOf(contents.getURL());
  const login = host && (readLogins(hoLoginsFile())[loginKey(store, host)] || findLogin(readLogins(), store, host));
  if (!login || !login.password || !safeStorage.isEncryptionAvailable()) return;
  let password;
  try { password = safeStorage.decryptString(Buffer.from(login.password, 'base64')); } catch { return; }
  const now = Date.now();
  const key = loginKey(store, host);
  const submit = Boolean(login.autoSubmit) && now - (lastSubmit.get(key) || 0) > SUBMIT_GAP_MS;
  const script = `(${fillLogin.toString()})(${JSON.stringify(login.username || '')}, ${JSON.stringify(password)}, ${submit})`;
  contents.executeJavaScript(script)
    .then((result) => { if (result === 'submitted') lastSubmit.set(key, now); })
    .catch(() => {});
}

function chromeBookmarks() {
  const base = path.join(process.env.LOCALAPPDATA || '', 'Google', 'Chrome', 'User Data');
  let profiles = [];
  try { profiles = fs.readdirSync(base).filter((d) => d === 'Default' || /^Profile \d+$/.test(d)); } catch { return []; }
  const found = [];
  const seen = new Set();
  const walk = (node) => {
    if (!node) return;
    if (node.type === 'url' && isWeb(node.url) && !seen.has(node.url)) {
      seen.add(node.url);
      found.push({ name: String(node.name || hostOf(node.url)).trim(), url: node.url });
    }
    (node.children || []).forEach(walk);
  };
  for (const profile of profiles) {
    try { walk(JSON.parse(fs.readFileSync(path.join(base, profile, 'Bookmarks'), 'utf8')).roots.bookmark_bar); } catch { /* profile without bookmarks */ }
  }
  return found;
}

// Each store session gets the Chrome UA and no permissions beyond fullscreen
// and clipboard-write.
const partitions = new Map();
function storeSession(partition) {
  if (!partitions.has(partition)) {
    const ses = session.fromPartition(partition);
    ses.setUserAgent(USER_AGENT);
    ses.setPermissionRequestHandler((_wc, permission, callback) => callback(permission === 'fullscreen' || permission === 'clipboard-sanitized-write'));
    partitions.set(partition, ses);
  }
  return partitions.get(partition);
}

function attach(win) {
  win.webContents.on('will-attach-webview', (event, webPreferences, params) => {
    delete webPreferences.preload;
    webPreferences.nodeIntegration = false;
    webPreferences.contextIsolation = true;
    webPreferences.sandbox = true;
    if (!PARTITION_RE.test(params.partition || '')) params.partition = PARTITION;
    storeSession(params.partition);
    if (!isWeb(params.src)) event.preventDefault();
  });
  win.webContents.on('did-attach-webview', (_event, contents) => {
    const partition = [...partitions].find(([, ses]) => ses === contents.session)?.[0] || PARTITION;
    const store = partition === PARTITION ? '' : partition.slice(PARTITION.length + 1);
    // Popups (report / print / lookup windows) open as their own windows in
    // the same store session, keeping window.opener for portals that pass
    // data back.
    contents.setWindowOpenHandler(({ url }) => (isWeb(url) || url === 'about:blank'
      ? { action: 'allow', overrideBrowserWindowOptions: { autoHideMenuBar: true, webPreferences: { partition, sandbox: true, contextIsolation: true, nodeIntegration: false } } }
      : { action: 'deny' }));
    contents.on('did-finish-load', () => autoLogin(contents, store));
    contents.on('did-navigate-in-page', (_e, _url, isMainFrame) => { if (isMainFrame) autoLogin(contents, store); });
  });
}

function init() {
  // Only the app's own page may call these (portal pages have no preload).
  const fromApp = (event) => event.sender.getType() === 'window';
  ipcMain.handle('web:logins', (event, { store } = {}) => (fromApp(event) ? publicLogins(store) : {}));
  ipcMain.handle('web:saveLogin', (event, { store, url, username, password, autoSubmit } = {}) => {
    if (!fromApp(event)) throw new Error('Not allowed.');
    const host = hostOf(url);
    if (!host) throw new Error('Enter the site address first.');
    const key = loginKey(store, host);
    const map = readLogins();
    const entry = { ...(map[key] || {}), username: String(username || '').trim(), autoSubmit: Boolean(autoSubmit) };
    if (password) {
      if (!safeStorage.isEncryptionAvailable()) throw new Error('Windows encryption is not available on this PC, so the password cannot be saved.');
      entry.password = safeStorage.encryptString(String(password)).toString('base64');
    }
    map[key] = entry;
    writeLogins(map);
    lastSubmit.delete(key);
    return publicLogins(store);
  });
  ipcMain.handle('web:clearLogin', (event, { store, url } = {}) => {
    if (!fromApp(event)) throw new Error('Not allowed.');
    const map = readLogins();
    delete map[loginKey(store, hostOf(url))];
    writeLogins(map);
    return publicLogins(store);
  });
  // The store's HO logins, resolved at HO (its own, else the supplier
  // level): replaces this store's cached set. First portal per site wins.
  ipcMain.handle('web:syncLogins', (event, { store, items, fresh } = {}) => {
    if (!fromApp(event)) throw new Error('Not allowed.');
    if (!storeKey(store)) return 0;
    if (!safeStorage.isEncryptionAvailable()) throw new Error('Windows encryption is not available on this PC, so portal logins cannot be kept here.');
    const prefix = `${storeKey(store)}|`;
    const map = readLogins(hoLoginsFile());
    Object.keys(map).filter((key) => key.startsWith(prefix)).forEach((key) => delete map[key]);
    for (const item of Array.isArray(items) ? items : []) {
      const key = loginKey(store, hostOf(item?.url));
      if (!hostOf(item?.url) || !item.password || map[key]) continue;
      map[key] = { username: String(item.username || ''), password: safeStorage.encryptString(String(item.password)).toString('base64'), autoSubmit: Boolean(item.autoSubmit) };
      if (fresh) lastSubmit.delete(key);
    }
    writeLogins(map, hoLoginsFile());
    return Object.keys(map).filter((key) => key.startsWith(prefix)).length;
  });
  ipcMain.handle('web:chromeBookmarks', (event) => (fromApp(event) ? chromeBookmarks() : []));
  ipcMain.handle('web:openExternal', (event, { url } = {}) => {
    if (fromApp(event) && isWeb(url)) shell.openExternal(url);
    return true;
  });
}

module.exports = { PARTITION, attach, init, partitionFor };
