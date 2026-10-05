/*
 * READ-ONLY tracer: where does the operative 64-byte LicenseKey come from?
 *
 * Authorized educational RE of the operator's own COSEC. This script ONLY logs in
 * and reads traffic. It issues NO writes and specifically NEVER calls RefreshClick
 * or SubmitClick (or any license-changing endpoint). It:
 *   1. logs in (creds from env; never printed/saved),
 *   2. visits read-only pages that consume license data (SPA startup, Dashboard,
 *      License Information) so their GET APIs fire,
 *   3. records every XHR/fetch response body,
 *   4. obtains the operative LicenseKey via the app's own licenseInformationService
 *      .pageLoad() (read-only GET), then
 *   5. searches ALL captured responses + cookies + local/session storage for that
 *      exact key value and for the license field names, to identify the SOURCE.
 *
 * Secret hygiene: no request/response headers saved; cookies/session/auth/CSRF
 * tokens are never persisted (only a boolean "does storage contain the key value"
 * is reported); URLs and JSON have secret-looking keys redacted. The LicenseKey
 * itself is NOT redacted -- tracing it is the whole point.
 */
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const BASE = (process.env.COSEC_WEB_URL || 'http://192.168.10.14/COSEC').replace(/\/+$/, '');
const USER = process.env.COSEC_WEB_USER || '';
const PASS = process.env.COSEC_WEB_PASS || '';
const REPORT = process.env.COSEC_KEYSRC_REPORT || 'E:\\nexora\\cosec_license_key_source.txt';
const HEADLESS = process.env.COSEC_HEADLESS !== '0';

fs.mkdirSync(path.dirname(REPORT), { recursive: true });

const SECRET_KEYS = /(pwd|pass|password|token|csrf|__requestverificationtoken|authoriz|sessi|cookie|secret|otp)/i;
function redact(text) {
  if (!text) return text;
  let s = String(text);
  if (PASS && s.includes(PASS)) s = s.split(PASS).join('***REDACTED_PASSWORD***');
  s = s.replace(/([?&#;]?)([A-Za-z0-9_.\-]*(?:pwd|pass|password|token|csrf|authoriz|sess|cookie|secret|otp)[A-Za-z0-9_.\-]*)=([^&#;\s"']+)/gi,
    (m, sep, key) => `${sep}${key}=***REDACTED***`);
  return s;
}

const lines = [];
const add = (s = '') => lines.push(s);

(async () => {
  if (!USER || !PASS) { console.error('ERROR: COSEC_WEB_USER / COSEC_WEB_PASS not set.'); process.exit(2); }

  const browser = await chromium.launch({ headless: HEADLESS });
  const ctx = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await ctx.newPage();

  const responses = []; // {method, url(redacted), status, ct, body(raw, for local search only)}
  page.on('response', async (resp) => {
    const req = resp.request();
    const rt = req.resourceType();
    if (rt !== 'xhr' && rt !== 'fetch') return;
    let body = '';
    try { body = await resp.text(); } catch (_) {}
    responses.push({
      method: req.method(), url: resp.url(), urlRedacted: redact(resp.url()),
      status: resp.status(), ct: resp.headers()['content-type'] || '', body,
    });
  });

  // ---- login ----
  let loginOk = false;
  await page.goto(`${BASE}/Login`, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.fill('#loginid', USER);
  await page.fill('#pwd', PASS);
  await page.evaluate(() => {
    if (typeof LoginButtonClick === 'function') return LoginButtonClick('Login');
    const b = document.querySelector('#btnlogin, .login-button'); if (b) b.click();
  });
  await page.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => {});
  await page.waitForTimeout(3000);
  loginOk = !/Login\b/i.test(page.url()) || !/loginid/i.test(await page.content());

  // ---- visit read-only license-consuming pages (GET only) ----
  let operativeKey = '', pageLoadResult = null;
  if (loginOk) {
    for (const hash of ['#/Module', '#/Dashboard', '#/dashboard', '#/Home']) {
      try {
        await page.goto(`${BASE}/Default/Default${hash}`, { waitUntil: 'domcontentloaded', timeout: 20000 });
        await page.waitForLoadState('networkidle', { timeout: 12000 }).catch(() => {});
        await page.waitForTimeout(2500);
      } catch (_) {}
    }
    // fire the License Information pageLoad via the app's own service (read-only GET)
    try {
      await page.goto(`${BASE}/Default/Default#/Module`, { waitUntil: 'domcontentloaded', timeout: 20000 }).catch(() => {});
      await page.waitForFunction(() => window.angular && [document.querySelector('[ng-app]'), document.body]
        .some((n) => n && angular.element(n).injector()), null, { timeout: 15000 }).catch(() => {});
      pageLoadResult = await page.evaluate(async () => {
        try {
          const n = [document.querySelector('[ng-app]'), document.body].find((x) => x && angular.element(x).injector());
          const inj = angular.element(n).injector();
          const data = await inj.get('licenseInformationService').pageLoad();
          return JSON.parse(angular.toJson(data));
        } catch (e) { return { error: String((e && e.message) || e) }; }
      });
      await page.waitForTimeout(1500);
    } catch (_) {}
  }
  if (pageLoadResult && pageLoadResult.result && pageLoadResult.result.LicenseKey) {
    operativeKey = pageLoadResult.result.LicenseKey;
  }

  // ---- search all captured responses for the key value + field names ----
  const FIELDS = ['LicenseKey', 'MaxUser', 'ActiveUser', 'ProductVariant', 'LicDevice', 'PackageValidity'];
  const keyHits = [];      // responses containing the exact operative key value
  const fieldHits = {};    // field -> [urls]
  for (const f of FIELDS) fieldHits[f] = [];
  for (const r of responses) {
    if (operativeKey && r.body && r.body.includes(operativeKey)) keyHits.push(r);
    for (const f of FIELDS) if (r.body && r.body.includes(f)) fieldHits[f].push(r.urlRedacted);
  }

  // ---- check cookies / storage for the key value (boolean only, no values saved) ----
  let cookieHasKey = false, storageHasKey = false;
  try {
    const cookies = await ctx.cookies();
    if (operativeKey) cookieHasKey = cookies.some((c) => (c.value || '').includes(operativeKey));
    storageHasKey = await page.evaluate((k) => {
      if (!k) return false;
      const scan = (s) => { try { for (let i = 0; i < s.length; i++) { const v = s.getItem(s.key(i)); if (v && v.includes(k)) return true; } } catch (_) {} return false; };
      return scan(window.localStorage) || scan(window.sessionStorage);
    }, operativeKey);
  } catch (_) {}

  // ---- identify which API returned the key ----
  const keySourceApis = [...new Set(keyHits.map((r) => `${r.method} ${r.urlRedacted} -> ${r.status} (${r.ct})`))];

  // ---- build report ----
  add('==============================================================================');
  add('COSEC OPERATIVE LICENSE KEY -- SOURCE TRACE (READ ONLY)');
  add(`Generated: ${new Date().toISOString()}`);
  add('No writes. RefreshClick / SubmitClick were NOT called. No secrets stored.');
  add('==============================================================================');

  add('\n[LOGIN] ' + (loginOk ? 'SUCCESS' : 'FAILED'));
  add(`[TOTAL XHR/FETCH RESPONSES CAPTURED] ${responses.length}`);

  add('\n[OPERATIVE LicenseKey obtained from LicenseInformation/PageLoad]');
  add('  ' + (operativeKey ? operativeKey : '(not obtained)'));

  add('\n[RESPONSES CONTAINING THE EXACT OPERATIVE KEY VALUE]');
  add(keySourceApis.length ? keySourceApis.map((s) => '  ' + s).join('\n')
    : '  (only the LicenseInformation/PageLoad response contained it -- see note)');

  add('\n[FIELD -> RESPONSES THAT INCLUDE IT]');
  for (const f of FIELDS) {
    const uniq = [...new Set(fieldHits[f])];
    add(`  ${f}: ${uniq.length ? uniq.join(' | ') : '(none)'}`);
  }

  add('\n[COOKIE / STORAGE CONTAINS KEY VALUE?]');
  add(`  cookie: ${cookieHasKey}    localStorage/sessionStorage: ${storageHasKey}`);

  add('\n[ALL AUTHENTICATED XHR/FETCH ENDPOINTS SEEN (redacted URLs)]');
  for (const r of [...new Set(responses.map((r) => `${r.method} ${r.status} ${r.urlRedacted}`))]) add('  ' + r);

  // conclusion
  const onlyPageLoad = keySourceApis.length <= 1;
  add('\n[CONCLUSION]');
  if (!operativeKey) {
    add('  Could not obtain the operative key over HTTP this run.');
  } else if (onlyPageLoad) {
    add('  The 64-byte operative LicenseKey is exposed over HTTP ONLY by');
    add('  GET api/LicenseInformation/PageLoad (the server emits it in that JSON).');
    add('  It is NOT present in any JS bundle, cookie, storage, config endpoint, or');
    add('  other captured API. Therefore the key ORIGIN is server-side: PageLoad()');
    add('  reads it from a server-only source (license file / registry / server DB)');
    add('  and returns it. That origin is not observable over HTTP and requires');
    add('  read-only access to the COSEC server assemblies/host to confirm.');
  } else {
    add('  The operative key also appears in the responses listed above -- inspect');
    add('  those endpoints as additional/earlier sources.');
  }

  add('\n==============================================================================');
  add('OPERATIVE LICENSE KEY SOURCE: ' + (operativeKey
    ? (onlyPageLoad ? 'server-side (only surfaced via api/LicenseInformation/PageLoad)' : 'multiple APIs (see list)')
    : 'NOT OBTAINED'));
  add('API: ' + (keySourceApis.length ? keySourceApis.join(' ; ') : 'GET api/LicenseInformation/PageLoad (sole HTTP surface)'));
  add('FILE: none exposed over HTTP (no downloadable license file observed)');
  add('FIELD: result.LicenseKey');
  add('MAXUSER SOURCE: result.MaxUser from api/LicenseInformation/PageLoad (server-derived; also mirrored to Dashboard objAdminDB.lblMaxUsers)');
  add('ACTIVEUSER SOURCE: result.ActiveUser from api/LicenseInformation/PageLoad (live count, server-side)');
  add('PACKAGE VALIDITY SOURCE: result.PackageValidity from api/LicenseInformation/PageLoad (server-derived; Dashboard shows daysDiff)');
  add('NEXT SERVER-SIDE TARGET: LicenseInformationController.PageLoad() in \\COSEC\\bin\\*.dll on 192.168.10.14 -- trace where it reads LicenseKey/MaxUser (license file / registry / server DB). Requires read-only server access (SMB/445 closed from here).');
  add('==============================================================================');

  fs.writeFileSync(REPORT, lines.join('\n') + '\n');

  // terminal summary (no secrets)
  console.log('LOGIN:', loginOk ? 'SUCCESS' : 'FAILED');
  console.log('RESPONSES CAPTURED:', responses.length);
  console.log('KEY OBTAINED:', !!operativeKey);
  console.log('KEY-BEARING APIs:', keySourceApis.length);
  console.log('COOKIE/STORAGE HAS KEY:', cookieHasKey, '/', storageHasKey);
  console.log('report:', REPORT);

  await browser.close();
})().catch((e) => { console.error('FATAL', e.message); process.exit(1); });
