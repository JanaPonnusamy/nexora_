// Store-level WhatsApp: THIS PC's own WhatsApp Web session, run in a hidden
// window inside the Stock Client, so a store sends its orders / stock files
// from its own number instead of HO's.
//
// The store links it once by scanning the QR shown on the app's WhatsApp
// screen; the session persists in the 'persist:store-whatsapp' partition
// (userData), so it survives app restarts like a normal browser login.
//
// Automation mirrors the HO backend's Playwright sender
// (backend/modules/whatsapp/service.py) -- same selectors, same "verify the
// right chat is open before sending" guard -- but drives the page through
// Chromium's DevTools protocol (webContents.debugger): real mouse/keyboard
// input (WhatsApp ignores synthetic JS clicks for some controls, and the file
// picker needs a trusted gesture) and file-chooser interception so attaching
// never pops a native dialog.
const path = require('node:path');
const fs = require('node:fs');
const os = require('node:os');
const { app, BrowserWindow, ipcMain, session, shell } = require('electron');

const PARTITION = 'persist:store-whatsapp';
const WA_URL = 'https://web.whatsapp.com/';
// Electron 22's own UA names Electron + Chrome 108, which WhatsApp Web may
// reject as an unsupported browser. A current desktop Chrome UA loads it
// normally (verified: QR renders on Electron 22.3.27).
const USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36';
const LOADING_STUCK_MS = 60000;
const LOG_LIMIT = 200;

let waWin = null;
let sendChain = Promise.resolve();
let sending = false;

const configPath = () => path.join(app.getPath('userData'), 'store-whatsapp.json');
const logPath = () => path.join(app.getPath('userData'), 'store-whatsapp-log.json');

function readJson(file, fallback) {
  try { return JSON.parse(fs.readFileSync(file, 'utf8')); } catch { return fallback; }
}
function writeJson(file, data) {
  try { fs.writeFileSync(file, JSON.stringify(data, null, 2), 'utf8'); } catch { /* best-effort */ }
}
const isEnabled = () => Boolean(readJson(configPath(), {}).enabled);
function setEnabled(enabled) { writeJson(configPath(), { ...readJson(configPath(), {}), enabled }); }

function recordSend(entry) {
  const log = readJson(logPath(), []);
  log.unshift({ at: new Date().toISOString(), ...entry });
  writeJson(logPath(), log.slice(0, LOG_LIMIT));
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// --- window / protocol ------------------------------------------------------

function ensureWindow() {
  if (waWin && !waWin.isDestroyed()) return waWin;
  waWin = new BrowserWindow({
    width: 1280,
    height: 900,
    show: false,
    title: 'Store WhatsApp',
    autoHideMenuBar: true,
    webPreferences: {
      partition: PARTITION,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      // Keep timers/rendering running while hidden -- WhatsApp Web stalls
      // (and sends never complete) if Chromium throttles a background page.
      backgroundThrottling: false
    }
  });
  const wc = waWin.webContents;
  wc.setUserAgent(USER_AGENT);
  // Links inside chats open in the real browser, never a new app window.
  wc.setWindowOpenHandler(({ url }) => {
    if (/^https?:/i.test(url)) shell.openExternal(url);
    return { action: 'deny' };
  });
  // Closing the (optionally shown) WhatsApp window only hides it; the session
  // keeps running for background sends. shutdown() destroys it for real.
  waWin.on('close', (event) => {
    if (!app.isQuitting && waWin && !waWin.isDestroyed()) {
      event.preventDefault();
      waWin.hide();
    }
  });
  waWin.on('closed', () => { waWin = null; });
  wc.on('render-process-gone', () => { try { wc.reload(); } catch { /* window going away */ } });
  try {
    wc.debugger.attach('1.3');
    // A hidden window is never "focused", so editors would ignore typed input.
    wc.debugger.sendCommand('Emulation.setFocusEmulationEnabled', { enabled: true }).catch(() => {});
    wc.debugger.sendCommand('Page.enable').catch(() => {});
  } catch { /* already attached */ }
  wc.loadURL(WA_URL, { userAgent: USER_AGENT }).catch(() => {});
  return waWin;
}

function cdp(method, params = {}) {
  return ensureWindow().webContents.debugger.sendCommand(method, params);
}

function js(expression) {
  return ensureWindow().webContents.executeJavaScript(expression, true);
}

// --- page state -------------------------------------------------------------

const STATE_JS = `(() => {
  if (document.querySelector("#pane-side") || document.querySelector("input[aria-label='Search or start a new chat']")) return { state: 'ready' };
  const reload = [...document.querySelectorAll("[role='button'],button")].find((b) => /reload/i.test(b.textContent || ''));
  if (reload) reload.click();
  const canvas = document.querySelector("canvas[aria-label*='Scan']") || document.querySelector("div[data-ref] canvas");
  if (canvas) { try { return { state: 'qr', qr: canvas.toDataURL('image/png') }; } catch { return { state: 'qr' }; } }
  return { state: 'loading' };
})()`;

async function pageState() {
  if (!waWin || waWin.isDestroyed()) return { state: 'off' };
  try { return await js(STATE_JS); } catch { return { state: 'loading' }; }
}

async function waitForState(ms) {
  const end = Date.now() + ms;
  let st = await pageState();
  while (st.state === 'loading' && Date.now() < end) {
    await sleep(1000);
    st = await pageState();
  }
  return st;
}

// Same recovery ladder as the HO sender's _settle_session: a page stuck on
// "Loading your chats" is reloaded, never reported as "not linked".
async function settle() {
  ensureWindow();
  let st = await waitForState(LOADING_STUCK_MS);
  if (st.state !== 'loading') return st;
  try { await ensureWindow().webContents.loadURL(WA_URL, { userAgent: USER_AGENT }); } catch { /* keep polling */ }
  st = await waitForState(LOADING_STUCK_MS);
  return st;
}

// --- input helpers ----------------------------------------------------------

// Find the first VISIBLE element matching any of the XPaths and return its
// on-screen centre (scrolling it into view first).
function locateJs(xpaths) {
  return `(() => {
    const xps = ${JSON.stringify(xpaths)};
    for (const xp of xps) {
      const snap = document.evaluate(xp, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
      for (let i = 0; i < snap.snapshotLength; i++) {
        const el = snap.snapshotItem(i);
        const r0 = el.getBoundingClientRect();
        if (!r0.width || !r0.height) continue;
        el.scrollIntoView({ block: 'center', inline: 'nearest' });
        const r = el.getBoundingClientRect();
        return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
      }
    }
    return null;
  })()`;
}

async function locate(xpaths, timeoutMs) {
  const end = Date.now() + timeoutMs;
  for (;;) {
    const pos = await js(locateJs(xpaths)).catch(() => null);
    if (pos) return pos;
    if (Date.now() >= end) return null;
    await sleep(300);
  }
}

async function clickAt({ x, y }) {
  await cdp('Input.dispatchMouseEvent', { type: 'mouseMoved', x, y });
  await cdp('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount: 1 });
  await cdp('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 1 });
}

async function clickFirst(xpaths, timeoutMs, what) {
  const pos = await locate(xpaths, timeoutMs);
  if (!pos) throw new Error(`WhatsApp ${what} not found.`);
  await clickAt(pos);
  return pos;
}

const KEYS = {
  Enter: { key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13, text: '\r' },
  Escape: { key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 },
  Backspace: { key: 'Backspace', code: 'Backspace', windowsVirtualKeyCode: 8 },
  a: { key: 'a', code: 'KeyA', windowsVirtualKeyCode: 65 }
};
// modifiers: 2 = Ctrl, 8 = Shift
async function press(name, modifiers = 0, commands) {
  const k = KEYS[name];
  const down = { type: k.text && !modifiers ? 'keyDown' : 'rawKeyDown', key: k.key, code: k.code,
    windowsVirtualKeyCode: k.windowsVirtualKeyCode, nativeVirtualKeyCode: k.windowsVirtualKeyCode, modifiers };
  if (k.text && !modifiers) down.text = k.text;
  if (commands) down.commands = commands;
  await cdp('Input.dispatchKeyEvent', down);
  await cdp('Input.dispatchKeyEvent', { type: 'keyUp', key: k.key, code: k.code,
    windowsVirtualKeyCode: k.windowsVirtualKeyCode, nativeVirtualKeyCode: k.windowsVirtualKeyCode, modifiers });
}

async function clearFocused() {
  await press('a', 2, ['selectAll']);
  await press('Backspace');
}

// Multi-line text: Shift+Enter between lines (plain Enter would send).
async function typeText(text) {
  const lines = String(text).split(/\r?\n/);
  for (let i = 0; i < lines.length; i++) {
    if (i) await press('Enter', 8);
    if (lines[i]) await cdp('Input.insertText', { text: lines[i] });
  }
}

// --- selectors (kept in step with backend/modules/whatsapp/service.py) -------

const SEARCH_BOX = [
  "//input[@aria-label='Search or start a new chat']",
  "//input[@type='text'][@data-tab='3']",
  "//div[@contenteditable='true'][@data-tab='3']",
  "//div[@contenteditable='true'][@role='textbox'][not(ancestor::footer)][not(@id='conversation-compose-box-input')][not(@data-tab='10')][not(@aria-placeholder='Type a message')]"
];
const COMPOSER = [
  "//footer//div[@contenteditable='true'][@data-tab='10']",
  "//div[@contenteditable='true'][starts-with(@aria-label,'Type a message')]",
  "//footer//div[@contenteditable='true']"
];
const ATTACH = [
  "//button[@aria-label='Attach']",
  "//*[@role='button'][@aria-label='Attach']",
  "//span[@data-icon='plus-rounded']",
  "//span[@data-icon='clip']",
  "//button[@title='Attach']"
];
const ATTACH_DOCUMENT = [
  "//div[@aria-label='Document']",
  "//li[@aria-label='Document']",
  "//li[.//span[normalize-space()='Document']]",
  "//span[normalize-space(text())='Document']",
  "//div[normalize-space(text())='Document']"
];
// Images go as photos (inline, all in ONE message), not as documents.
const ATTACH_MEDIA = [
  "//div[@aria-label='Photos & videos']",
  "//li[@aria-label='Photos & videos']",
  "//li[.//span[normalize-space()='Photos & videos']]",
  "//span[normalize-space(text())='Photos & videos']",
  "//div[normalize-space(text())='Photos & videos']"
];
const PREVIEW_CAPTION = [
  "//div[@aria-label='Add a caption'][@contenteditable='true']",
  "//div[@contenteditable='true'][@data-tab='10'][not(ancestor::footer)]"
];
// File-preview send control is <div role="button" aria-label="Send 1 selected">
// in the 2026-10 build; voice-message buttons excluded.
const SEND_BUTTON = [
  "//button[@aria-label='Send']",
  "//*[@role='button'][@aria-label='Send']",
  "//*[self::button or @role='button'][starts-with(@aria-label,'Send ')][not(contains(@aria-label,'oice'))]",
  "//span[@data-icon='send']",
  "//span[starts-with(@data-icon,'wds-ic-send')]"
];
const STARTUP_DIALOG_BUTTONS = [
  "//div[@role='dialog']//*[self::button or @role='button'][normalize-space()='Continue' or normalize-space()='OK' or normalize-space()='Got it' or normalize-space()='Okay']",
  "//div[@role='dialog']//*[@aria-label='Close']"
];

async function dismissDialogs() {
  for (let i = 0; i < 3; i++) {
    const open = await js("!!document.querySelector(\"div[role='dialog']\")").catch(() => false);
    if (!open) return;
    const pos = await locate(STARTUP_DIALOG_BUTTONS, 500);
    if (pos) await clickAt(pos); else await press('Escape');
    await sleep(500);
  }
}

const currentChatTitleJs = `(() => {
  const el = document.querySelector("#main header span[data-testid='conversation-info-header-chat-title']")
    || [...document.querySelectorAll('#main header span[title]')].find((s) => !s.closest("div[data-testid='chat-subtitle']"));
  return el ? (el.getAttribute('title') || el.textContent || '').trim() : '';
})()`;

function titlesMatch(opened, label) {
  const a = String(opened || '').trim().toLowerCase();
  const b = String(label || '').trim().toLowerCase();
  return Boolean(a && b) && (a === b || a.includes(b) || b.includes(a));
}

function phoneDigits(chat) {
  const raw = String(chat || '').trim();
  if (!/^[+\d][\d\s()-]{7,}$/.test(raw)) return '';
  let digits = raw.replace(/\D/g, '');
  if (digits.length === 10) digits = `91${digits}`; // bare Indian mobile
  return digits.length >= 11 ? digits : '';
}

// --- chat opening -----------------------------------------------------------

async function openChat(chat) {
  const digits = phoneDigits(chat);
  if (digits) {
    await ensureWindow().webContents.loadURL(`${WA_URL}send?phone=${digits}`, { userAgent: USER_AGENT });
    const st = await settle();
    if (st.state !== 'ready') throw new Error('WhatsApp did not finish loading.');
    const composer = await locate(COMPOSER, 45000);
    if (!composer) {
      const invalid = await js("/invalid/i.test(document.body.innerText || '')").catch(() => false);
      throw new Error(invalid ? `${chat} is not on WhatsApp.` : `Could not open a chat with ${chat}.`);
    }
    return;
  }

  const label = String(chat).trim();
  const lower = JSON.stringify(label.toLowerCase());
  const up = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
  const lo = 'abcdefghijklmnopqrstuvwxyz';
  // Only the row's own title cell -- never the last-message preview, which
  // can quote another group's name (see the HO sender's wrong-group fix).
  const cell = "//div[@id='pane-side']//div[@data-testid='cell-frame-title']";
  const results = [
    `${cell}//span[@title=${JSON.stringify(label)}]`,
    `${cell}//span[translate(@title,'${up}','${lo}')=${lower}]`,
    `${cell}//span[contains(translate(@title,'${up}','${lo}'),${lower})]`
  ];
  let lastOpened = '';
  for (let attempt = 0; attempt < 3; attempt++) {
    if (attempt) { await press('Escape'); await sleep(500); }
    await clickFirst(SEARCH_BOX, 15000, 'search box');
    await clearFocused();
    await cdp('Input.insertText', { text: label });
    await sleep(600);
    const row = await locate(results, 10000);
    if (!row) {
      if (attempt === 2) throw new Error(`No WhatsApp chat named "${label}" was found. Use the exact chat/group name.`);
      continue;
    }
    await clickAt(row);
    const end = Date.now() + 10000;
    while (Date.now() < end) {
      lastOpened = await js(currentChatTitleJs).catch(() => '');
      if (titlesMatch(lastOpened, label)) return;
      await sleep(200);
    }
  }
  throw new Error(`Opened chat "${lastOpened || 'unknown'}" is not "${label}" -- not sent, to avoid the wrong chat.`);
}

// --- sending ----------------------------------------------------------------

async function waitPendingUploads(timeoutMs) {
  // A just-sent message shows a clock icon until WhatsApp has delivered it to
  // its server; leaving earlier (or quitting the app) can lose the upload.
  // Not fatal on timeout: the message already left the composer/preview, and
  // an older stuck message in the chat must not turn this send into a
  // "failed" that someone then re-sends as a duplicate.
  const end = Date.now() + timeoutMs;
  while (Date.now() < end) {
    const pending = await js("!!document.querySelector(\"#main span[data-icon='msg-time'], #main span[data-icon='status-time']\")").catch(() => false);
    if (!pending) return;
    await sleep(1000);
  }
}

function chooseFile(filePath, option = ATTACH_DOCUMENT, what = '"Document" attach option') {
  const files = Array.isArray(filePath) ? filePath : [filePath];
  const wc = ensureWindow().webContents;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => { cleanup(); reject(new Error('file chooser did not open')); }, 10000);
    const onMessage = (_event, method, params) => {
      if (method !== 'Page.fileChooserOpened') return;
      cleanup();
      wc.debugger.sendCommand('DOM.setFileInputFiles', { files, backendNodeId: params.backendNodeId })
        .then(resolve, reject);
    };
    function cleanup() {
      clearTimeout(timer);
      wc.debugger.removeListener('message', onMessage);
      wc.debugger.sendCommand('Page.setInterceptFileChooserDialog', { enabled: false }).catch(() => {});
    }
    wc.debugger.on('message', onMessage);
    wc.debugger.sendCommand('Page.setInterceptFileChooserDialog', { enabled: true })
      .then(() => clickFirst(option, 5000, what))
      .catch((err) => { cleanup(); reject(err); });
  });
}

async function attachFallback(filePath, media = false) {
  // Older UI: no Document menu/chooser -- set the hidden <input type=file>.
  const files = Array.isArray(filePath) ? filePath : [filePath];
  const pick = media
    ? "[...document.querySelectorAll(\"input[type='file'][accept*='image']\")].pop() || [...document.querySelectorAll(\"input[type='file']\")].pop() || null"
    : "[...document.querySelectorAll(\"input[type='file']\")].pop() || null";
  const { result } = await cdp('Runtime.evaluate', { expression: pick });
  if (!result || !result.objectId) throw new Error('No file input was found to attach the file.');
  await cdp('DOM.setFileInputFiles', { files, objectId: result.objectId });
}

// filePath: one path, or several image paths sent together as ONE message.
async function sendFile(filePath, caption, media = false) {
  await clickFirst(ATTACH, 15000, 'attach button');
  await sleep(400);
  try {
    if (media) await chooseFile(filePath, ATTACH_MEDIA, '"Photos & videos" attach option');
    else await chooseFile(filePath);
  } catch {
    await attachFallback(filePath, media);
  }
  const send = await locate(SEND_BUTTON, 30000);
  if (!send) throw new Error('WhatsApp attachment preview did not open.');
  if (caption) {
    await clickFirst(PREVIEW_CAPTION, 5000, 'caption box').catch(() => {});
    await typeText(caption);
  }
  await clickAt(await locate(SEND_BUTTON, 5000) || send);
  // The preview closes once WhatsApp has taken the file.
  const end = Date.now() + 20000;
  while (Date.now() < end) {
    if (!(await locate(SEND_BUTTON.slice(1, 3), 0))) return;
    await sleep(500);
  }
  throw new Error('Attachment preview did not close after Send -- the file was not sent.');
}

async function sendText(text) {
  await clickFirst(COMPOSER, 15000, 'message box');
  await clearFocused();
  await typeText(text);
  await press('Enter');
  const end = Date.now() + 10000;
  while (Date.now() < end) {
    const empty = await js("(() => { const c = document.querySelector(\"footer div[contenteditable='true']\"); return !c || !(c.textContent || '').trim(); })()").catch(() => true);
    if (empty) return;
    await sleep(300);
  }
  throw new Error('Message did not leave the message box.');
}

const stageDir = () => {
  const dir = path.join(os.tmpdir(), 'nexora-store-whatsapp');
  fs.mkdirSync(dir, { recursive: true });
  return dir;
};

// payload: { chat, text?, paths?: [absolutePath], files?: [{ name, base64 }], source? }
async function doSend(payload) {
  const chat = String(payload.chat || '').trim();
  if (!chat) throw new Error('Choose a WhatsApp chat, group or number.');
  const paths = [...(payload.paths || [])];
  for (const f of payload.files || []) {
    const safe = String(f.name || 'file').replace(/[\\/:*?"<>|]+/g, '_');
    const p = path.join(stageDir(), `${Date.now()}_${safe}`);
    fs.writeFileSync(p, Buffer.from(f.base64, 'base64'));
    paths.push(p);
  }
  for (const p of paths) if (!fs.existsSync(p)) throw new Error(`File not found: ${p}`);
  // Owner rule: never a .zip on WhatsApp -- send the images / sheets themselves.
  if (paths.some((p) => /\.zip$/i.test(p))) throw new Error('Zip files are not sent on WhatsApp -- send the files inside it.');
  if (!paths.length && !String(payload.text || '').trim()) throw new Error('Nothing to send.');

  setEnabled(true);
  const st = await settle();
  if (st.state === 'qr') throw new Error('WhatsApp is not linked on this PC. Open the WhatsApp screen and scan the QR code.');
  if (st.state !== 'ready') throw new Error('WhatsApp Web is still loading. Try again in a minute.');
  await dismissDialogs();
  await openChat(chat);
  if (paths.length) {
    // All images in ONE message (one attach, one Send); other files after.
    const images = paths.filter((p) => /\.(png|jpe?g)$/i.test(p));
    const others = paths.filter((p) => !images.includes(p));
    let caption = payload.text;
    if (images.length) { await sendFile(images, caption, true); caption = ''; }
    for (const p of others) { await sendFile(p, caption); caption = ''; }
  } else {
    await sendText(payload.text);
  }
  await waitPendingUploads(90000);
}

function send(payload) {
  // One send at a time: they all drive the same page.
  const run = sendChain.then(async () => {
    sending = true;
    const names = [...(payload.paths || []).map((p) => path.basename(p)), ...(payload.files || []).map((f) => f.name)];
    try {
      await doSend(payload);
      recordSend({ chat: payload.chat, files: names, text: (payload.text || '').slice(0, 120), source: payload.source || '', status: 'sent' });
      return { status: 'sent' };
    } catch (err) {
      const message = err?.message || String(err);
      recordSend({ chat: payload.chat, files: names, text: (payload.text || '').slice(0, 120), source: payload.source || '', status: 'failed', error: message });
      return { status: 'failed', error: message };
    } finally {
      sending = false;
    }
  });
  sendChain = run.catch(() => {});
  return run;
}

// --- chat list / search (supplier contact picker) ---------------------------
// Same approach as the HO sender's list_chats: one JS pass per scroll over
// #pane-side reading each row's title cell; groups are labelled from the
// "Groups" filter chip (cached for the session, since search results carry
// no reliable group marker).

const FILTER_GROUPS = [
  "//button[@role='tab'][starts-with(normalize-space(.),'Groups') or starts-with(normalize-space(.),'Group')]",
  "//*[@role='tab'][contains(translate(.,'GROUP','group'),'group')]"
];
const FILTER_ALL = ["//button[@id='all-filter']", "//*[@role='tab'][normalize-space()='All']"];

const SCRAPE_NAMES_JS = `(() => {
  const pane = document.getElementById('pane-side');
  if (!pane) return [];
  const cells = pane.querySelectorAll("div[data-testid='cell-frame-title'] span[title]");
  const nodes = cells.length ? cells : pane.querySelectorAll('[role="listitem"] span[title], [role="row"] span[title]');
  const out = [];
  nodes.forEach((s) => { const t = (s.getAttribute('title') || '').trim(); if (t && !out.includes(t)) out.push(t); });
  return out;
})()`;
const SCROLL_PANE_JS = `(() => { const p = document.getElementById('pane-side'); if (!p) return;
  const g = p.querySelector('[role="grid"]'); [p, g].forEach((el) => { if (el) el.scrollTop = el.scrollHeight; }); })()`;
const TOP_PANE_JS = `(() => { const p = document.getElementById('pane-side'); if (!p) return;
  const g = p.querySelector('[role="grid"]'); [p, g].forEach((el) => { if (el) el.scrollTop = 0; }); })()`;

let groupNames = null;

async function scrapeNames(budgetMs, max = 800) {
  await js(TOP_PANE_JS).catch(() => {});
  await sleep(250);
  const names = [];
  const end = Date.now() + budgetMs;
  let stagnant = 0;
  while (Date.now() < end && names.length < max && stagnant < 3) {
    const batch = await js(SCRAPE_NAMES_JS).catch(() => []);
    let added = 0;
    for (const n of batch || []) if (!names.includes(n)) { names.push(n); added++; }
    stagnant = added ? 0 : stagnant + 1;
    await js(SCROLL_PANE_JS).catch(() => {});
    await sleep(300);
  }
  return names;
}

async function loadGroupNames(force) {
  if (groupNames && !force) return groupNames;
  const pos = await locate(FILTER_GROUPS, 3000);
  if (!pos) return groupNames || new Set();
  await clickAt(pos);
  await sleep(700);
  groupNames = new Set(await scrapeNames(12000));
  const all = await locate(FILTER_ALL, 2000);
  if (all) { await clickAt(all); await sleep(500); }
  return groupNames;
}

// opts: { query?, filter?: 'all'|'groups'|'contacts', refresh? }
async function doListChats(opts) {
  const st = await settle();
  if (st.state === 'qr') throw new Error('WhatsApp is not linked on this PC. Scan the QR code first.');
  if (st.state !== 'ready') throw new Error('WhatsApp Web is still loading. Try again in a minute.');
  await dismissDialogs();
  const groups = await loadGroupNames(Boolean(opts.refresh));
  const query = String(opts.query || '').trim();
  let names;
  if (query) {
    await clickFirst(SEARCH_BOX, 15000, 'search box');
    await clearFocused();
    await cdp('Input.insertText', { text: query });
    await sleep(1500);
    names = await scrapeNames(4000, 100);
    await clickFirst(SEARCH_BOX, 3000, 'search box').catch(() => {});
    await clearFocused().catch(() => {});
    await press('Escape').catch(() => {});
  } else {
    names = await scrapeNames(12000);
    for (const g of groups) if (!names.includes(g)) names.push(g);
  }
  const chats = names.map((name) => ({ name, kind: groups.has(name) ? 'group' : 'contact' }));
  const filter = opts.filter || 'all';
  return chats.filter((c) => filter === 'all' || (filter === 'groups' ? c.kind === 'group' : c.kind === 'contact'));
}

function listChats(opts = {}) {
  // Shares the send queue: both drive the same page.
  const run = sendChain.then(() => doListChats(opts).then((chats) => ({ chats }), (err) => ({ chats: [], error: err?.message || String(err) })));
  sendChain = run.catch(() => {});
  return run;
}

// --- lifecycle / IPC --------------------------------------------------------

async function status() {
  if (!waWin || waWin.isDestroyed()) return { state: isEnabled() ? 'starting' : 'off', enabled: isEnabled() };
  const st = await pageState();
  return { ...st, enabled: isEnabled(), sending, visible: waWin.isVisible() };
}

function shutdown() {
  if (waWin && !waWin.isDestroyed()) waWin.destroy();
  waWin = null;
}

function init() {
  app.on('before-quit', () => { app.isQuitting = true; });
  ipcMain.handle('wa:status', () => status());
  ipcMain.handle('wa:enable', () => { setEnabled(true); ensureWindow(); return status(); });
  ipcMain.handle('wa:disable', () => { setEnabled(false); shutdown(); return status(); });
  ipcMain.handle('wa:show', () => { const w = ensureWindow(); w.show(); w.focus(); return true; });
  ipcMain.handle('wa:unlink', async () => {
    shutdown();
    await session.fromPartition(PARTITION).clearStorageData();
    if (isEnabled()) ensureWindow();
    return status();
  });
  ipcMain.handle('wa:send', (_event, payload) => send(payload || {}));
  ipcMain.handle('wa:log', () => readJson(logPath(), []));
  ipcMain.handle('wa:chats', (_event, opts) => listChats(opts || {}));
  // Saved export files as base64, for sending through HO's WhatsApp profile.
  ipcMain.handle('wa:readFiles', (_event, paths) => (paths || []).map((p) => ({ name: path.basename(p), base64: fs.readFileSync(p).toString('base64') })));
  // Only start the (~300 MB) WhatsApp page on PCs that have linked it.
  if (isEnabled()) setTimeout(() => ensureWindow(), 8000);
}

module.exports = { init, shutdown };
