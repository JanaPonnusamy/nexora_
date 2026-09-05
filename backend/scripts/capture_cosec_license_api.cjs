/*
 * READ-ONLY capture of the COSEC License Information API wiring via Playwright.
 *
 * Authorized reverse-engineering of the operator's own COSEC install. This script
 * only LOADS pages and READS network traffic. It performs NO writes to COSEC and
 * NO database changes, and submits NO license changes.
 *
 * SECRET HYGIENE (hard requirement):
 *   - Credentials are read ONLY from env (COSEC_WEB_USER / COSEC_WEB_PASS); never
 *     hard-coded, never printed, never written to any output file.
 *   - Request/response headers are NOT saved. Cookies, Authorization headers,
 *     Set-Cookie, session ids and CSRF tokens are never persisted.
 *   - Request bodies and URLs are passed through a redactor that masks the
 *     password and common secret-bearing keys before anything is written.
 *
 * Usage:
 *   COSEC_WEB_URL, COSEC_WEB_USER, COSEC_WEB_PASS in env
 *   NODE_PATH=<npx playwright node_modules>  node backend/scripts/capture_cosec_license_api.cjs
 */
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const BASE = (process.env.COSEC_WEB_URL || 'http://192.168.10.14/COSEC').replace(/\/+$/, '');
const USER = process.env.COSEC_WEB_USER || '';
const PASS = process.env.COSEC_WEB_PASS || '';
const REPORT = process.env.COSEC_CAP_REPORT || 'E:\\nexora\\cosec_license_api_capture.txt';
const JS_DIR = process.env.COSEC_CAP_DIR ||
  path.join(process.env.TEMP || '.', 'cosec_capture');
const HEADLESS = process.env.COSEC_HEADLESS !== '0';

fs.mkdirSync(JS_DIR, { recursive: true });
fs.mkdirSync(path.dirname(REPORT), { recursive: true });

// ---- redaction --------------------------------------------------------------
const SECRET_KEYS = /(pwd|pass|password|token|csrf|__requestverificationtoken|auth|sessi|cookie|secret|otp)/i;
function redact(text) {
  if (!text) return text;
  let s = String(text);
  if (PASS && s.includes(PASS)) s = s.split(PASS).join('***REDACTED_PASSWORD***');
  // mask key=value pairs whose key looks secret (query strings / form bodies)
  s = s.replace(/([?&#;]?)([A-Za-z0-9_.\-]*(?:pwd|pass|password|token|csrf|auth|sess|cookie|secret|otp)[A-Za-z0-9_.\-]*)=([^&#;\s"']+)/gi,
    (m, sep, key) => `${sep}${key}=***REDACTED***`);
  return s;
}
function redactJsonMaybe(text) {
  try {
    const obj = JSON.parse(text);
    const walk = (o) => {
      if (o && typeof o === 'object') {
        for (const k of Object.keys(o)) {
          if (SECRET_KEYS.test(k)) o[k] = '***REDACTED***';
          else walk(o[k]);
        }
      }
    };
    walk(obj);
    return JSON.stringify(obj, null, 2);
  } catch (_) {
    return redact(text);
  }
}

const lines = [];
const add = (s = '') => lines.push(s);

(async () => {
  if (!USER || !PASS) {
    console.error('ERROR: COSEC_WEB_USER / COSEC_WEB_PASS not set in env.');
    process.exit(2);
  }

  const browser = await chromium.launch({ headless: HEADLESS });
  const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await ctx.newPage();

  const jsFiles = [];      // {url, len, hasAPI}
  const xhrEvents = [];    // {method, url(redacted), status, reqBody(redacted), respType, respBody(redacted)}
  const pending = new Map();

  page.on('request', (req) => {
    const rt = req.resourceType();
    if (rt === 'xhr' || rt === 'fetch') {
      let body = '';
      try { body = req.postData() || ''; } catch (_) {}
      pending.set(req, { method: req.method(), url: redact(req.url()), reqBody: redact(body) });
    }
  });

  page.on('response', async (resp) => {
    const req = resp.request();
    const rt = req.resourceType();
    const url = resp.url();
    try {
      if (rt === 'script' || /\.js(\?|$)/i.test(url)) {
        let body = '';
        try { body = await resp.text(); } catch (_) {}
        const hasAPI = /licenseInformation(API|Controller|Service)/.test(body);
        jsFiles.push({ url: redact(url), len: body.length, hasAPI });
        if (hasAPI) {
          const fname = 'js_' + (url.split('/').pop().split('?')[0] || 'module').replace(/[^\w.]/g, '_');
          // JS source is application code (no secrets); still run through redactor defensively.
          fs.writeFileSync(path.join(JS_DIR, fname), redact(body));
        }
      } else if (rt === 'xhr' || rt === 'fetch') {
        const meta = pending.get(req) || { method: req.method(), url: redact(url), reqBody: '' };
        const ct = (resp.headers()['content-type'] || '');
        let respBody = '';
        try { respBody = await resp.text(); } catch (_) {}
        const respOut = /json/i.test(ct) ? redactJsonMaybe(respBody) : redact(respBody.slice(0, 4000));
        xhrEvents.push({ ...meta, status: resp.status(), respType: ct, respBody: respOut });
        pending.delete(req);
      }
    } catch (_) {}
  });

  // ---- 1. Login -------------------------------------------------------------
  let loginOk = false;
  let loginDiag = '';
  let inPageResult = null;
  try {
    await page.goto(`${BASE}/Login`, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.fill('#loginid', USER);
    await page.fill('#pwd', PASS);
    const clicked = await page.evaluate(() => {
      // COSEC's real login control runs client-side password encryption then submits.
      if (typeof LoginButtonClick === 'function') { LoginButtonClick('Login'); return 'LoginButtonClick(Login)'; }
      const b = document.querySelector('#btnlogin, .login-button');
      if (b) { b.click(); return b.outerHTML.slice(0, 120); }
      const f = document.querySelector('#frmLogin'); if (f) { f.submit(); return 'form.submit()'; }
      return '';
    });
    await page.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => {});
    await page.waitForTimeout(3000);
    const url = page.url();
    const html = await page.content();
    const stillLogin = /Login\b/i.test(url) && /frmLogin|Pwd|loginid/i.test(html);
    loginOk = !stillLogin;
    // grab any visible login error/validation text (helps tell bad-password from mechanics)
    let errText = '';
    try {
      errText = await page.evaluate(() => {
        const sel = ['.validation-summary-errors', '.field-validation-error', '#lblMessage',
                     '.login-error', '.error', '[id*=Error]', '[id*=Message]'];
        for (const s of sel) {
          const el = document.querySelector(s);
          if (el && el.innerText && el.innerText.trim()) return el.innerText.trim().slice(0, 200);
        }
        return '';
      });
    } catch (_) {}
    loginDiag = `trigger=${clicked || 'none'}; post-login-url=${url}; stillLoginPage=${stillLogin}` +
                (errText ? `; pageMessage="${errText}"` : '');
  } catch (e) {
    loginDiag = 'login exception: ' + e.message;
  }

  // ---- 2/3. Navigate to the License Information module -----------------------
  if (loginOk) {
    const targets = [
      `${BASE}/Default/Default#/Module`,
      `${BASE}/WebForms/frmLicensing.aspx`,
    ];
    for (const t of targets) {
      try {
        await page.goto(t, { waitUntil: 'domcontentloaded', timeout: 25000 });
        await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});
        await page.waitForTimeout(3500);
      } catch (_) {}
    }
    // try clicking any License menu entry in the SPA as a fallback
    try {
      const link = page.locator('a, span, li, div', { hasText: /licens/i }).first();
      if (await link.count()) { await link.click({ timeout: 4000 }).catch(() => {}); await page.waitForTimeout(3500); }
    } catch (_) {}

    // Drive the app's OWN Angular service to fire the real (read-only GET) pageLoad,
    // so we capture the live response + the exact token-bearing URL. No forged calls.
    // Stay on the already-bootstrapped post-login page (do NOT re-navigate, which
    // would drop the running app and leave no injector).
    try {
      await page.goto(`${BASE}/Default/Default#/Module`, { waitUntil: 'domcontentloaded', timeout: 25000 }).catch(() => {});
      await page.waitForFunction(() => {
        if (!window.angular) return false;
        const nodes = [document.querySelector('[ng-app]'), document.body, document.documentElement];
        return nodes.some((n) => n && angular.element(n).injector());
      }, null, { timeout: 20000 }).catch(() => {});
      inPageResult = await page.evaluate(async () => {
        try {
          if (!window.angular) return { error: 'angular not present' };
          const nodes = [document.querySelector('[ng-app]'), document.body, document.documentElement];
          let inj = null;
          for (const n of nodes) { if (n && angular.element(n).injector()) { inj = angular.element(n).injector(); break; } }
          if (!inj) return { error: 'no injector' };
          const svc = inj.get('licenseInformationService');
          const api = inj.get('licenseInformationAPI');
          const data = await svc.pageLoad();               // real GET via $resource
          // angular.toJson strips $-prefixed props ($promise/$$state) -> no cycles
          const clean = JSON.parse(angular.toJson(data));
          return { api, keys: Object.keys(clean || {}), sample: clean };
        } catch (e) { return { error: String((e && e.message) || e) }; }
      });
      await page.waitForTimeout(1500);
    } catch (_) {}
  }

  // ---- 4. Extract licenseInformationAPI.pageLoad / .openFile from loaded JS --
  let pageLoadApi = '', openFileApi = '', apiJsFile = '', apiSnippet = '';
  for (const f of fs.readdirSync(JS_DIR)) {
    if (!f.startsWith('js_')) continue;
    const src = fs.readFileSync(path.join(JS_DIR, f), 'utf8');
    if (!/licenseInformationAPI/.test(src)) continue;
    apiJsFile = f;
    // Isolate the licenseInformationAPI constant object specifically, so we don't
    // accidentally read pageLoad/openFile from an adjacent API constant.
    const objMatch = src.match(/licenseInformationAPI["']?\s*,\s*(\{[^}]*\})/) ||
                     src.match(/licenseInformationAPI\s*[=:]\s*(\{[^}]*\})/);
    if (objMatch) {
      apiSnippet = 'licenseInformationAPI = ' + objMatch[1];
      const scope = objMatch[1];
      const pl = scope.match(/pageLoad\s*:\s*["'`]([^"'`]+)["'`]/);
      const of = scope.match(/openFile\s*:\s*["'`]([^"'`]+)["'`]/);
      if (pl) pageLoadApi = pl[1];
      if (of) openFileApi = of[1];
    }
  }

  // ---- 5/6. Build report ----------------------------------------------------
  const licenseJs = jsFiles.filter((j) => j.hasAPI).map((j) => j.url);
  const licenseXhr = xhrEvents.filter((x) => /licens/i.test(x.url) || /licens/i.test(x.reqBody || ''));

  add('==============================================================================');
  add('COSEC LICENSE INFORMATION -- LIVE API CAPTURE (READ ONLY, SECRETS REDACTED)');
  add(`Generated: ${new Date().toISOString()}`);
  add(`Base: ${BASE}`);
  add('No password/cookie/session/auth-header/CSRF value is stored in this file.');
  add('==============================================================================');

  add('\n[LOGIN]');
  add('  result: ' + (loginOk ? 'SUCCESS' : 'FAILED'));
  add('  diag  : ' + loginDiag);

  add('\n[JS RESOURCES containing licenseInformation*]');
  add(licenseJs.length ? licenseJs.map((u) => '  ' + u).join('\n') : '  (none captured)');

  add('\n[licenseInformationAPI definition]');
  add('  source file (saved): ' + (apiJsFile || '(not found)'));
  add('  object snippet     : ' + (apiSnippet ? '\n' + apiSnippet : '(not found)'));
  add('  pageLoad endpoint  : ' + (pageLoadApi || '(not found in JS)'));
  add('  openFile endpoint  : ' + (openFileApi || '(not found in JS)'));

  add('\n[LICENSE-RELATED XHR/FETCH captured]');
  if (!licenseXhr.length) add('  (none matched /licens/ -- see all-XHR section below)');
  for (const x of licenseXhr) {
    add(`  ${x.method} ${x.url}  -> ${x.status}  (${x.respType})`);
    if (x.reqBody) add('    request body : ' + x.reqBody);
    add('    response body:');
    add(x.respBody.split('\n').map((l) => '      ' + l).join('\n'));
  }

  add('\n[LIVE pageLoad RESPONSE via app Angular service (read-only GET)]');
  if (inPageResult) {
    if (inPageResult.error) {
      add('  error: ' + inPageResult.error);
    } else {
      add('  licenseInformationAPI (from injector): ' + JSON.stringify(inPageResult.api));
      add('  response top-level keys: ' + JSON.stringify(inPageResult.keys));
      add('  response (secret-keys redacted):');
      add(redactJsonMaybe(JSON.stringify(inPageResult.sample)).split('\n').map((l) => '    ' + l).join('\n'));
    }
  } else {
    add('  (not captured)');
  }

  add('\n[ALL XHR/FETCH (URLs redacted) -- for context]');
  for (const x of xhrEvents.slice(0, 80)) add(`  ${x.method} ${x.status} ${x.url}`);

  add('\n[ALL JS RESOURCES loaded (URLs) -- for context]');
  for (const j of jsFiles.slice(0, 120)) add(`  ${j.hasAPI ? '*' : ' '} ${j.url}`);

  add('\n==============================================================================');
  add('LOGIN: ' + (loginOk ? 'SUCCESS' : 'FAILED'));
  add('LICENSE JS: ' + (apiJsFile || (licenseJs[0] || 'NOT CAPTURED')));
  add('PAGELOAD API: ' + (pageLoadApi || 'NOT FOUND'));
  add('OPENFILE API: ' + (openFileApi || 'NOT FOUND'));
  const respSummary = (inPageResult && !inPageResult.error && inPageResult.keys)
    ? ('keys=' + JSON.stringify(inPageResult.keys))
    : (licenseXhr[0] ? `${licenseXhr[0].status} ${licenseXhr[0].respType}` : 'NOT CAPTURED');
  add('LICENSE RESPONSE: ' + respSummary);
  add('NEXT STEP: server-side static inspection of the ASP.NET assembly implementing the pageLoad action on 192.168.10.14 (/bin), which is unreachable from this host (SMB closed).');
  add('==============================================================================');

  fs.writeFileSync(REPORT, lines.join('\n') + '\n');

  // ---- terminal: print ONLY the required summary (no secrets) ---------------
  console.log('LOGIN: ' + (loginOk ? 'SUCCESS' : 'FAILED'));
  console.log('LICENSE JS: ' + (apiJsFile || (licenseJs[0] || 'NOT CAPTURED')));
  console.log('PAGELOAD API: ' + (pageLoadApi || 'NOT FOUND'));
  console.log('OPENFILE API: ' + (openFileApi || 'NOT FOUND'));
  console.log('LICENSE RESPONSE: ' + respSummary);
  console.log('NEXT STEP: static inspection of server-side ASP.NET assembly on 192.168.10.14 (/bin) -- unreachable from this host (SMB closed).');
  console.log('(report: ' + REPORT + ')');

  await browser.close();
})().catch((e) => { console.error('FATAL', e.message); process.exit(1); });
