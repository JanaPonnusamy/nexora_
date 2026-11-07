import assert from 'node:assert/strict';
import { test } from 'node:test';
import { webFindSupplier, webHost, webLogin, webMergeSites, webMoveSite, webPortalFor, webPortalSites, webSupplierOption, webUrl } from './webPanelView.js';

test('address text becomes a loadable url', () => {
  assert.equal(webUrl('erd.puranisupplies.com/BB15SE/Backbone/admin/login.aspx'), 'https://erd.puranisupplies.com/BB15SE/Backbone/admin/login.aspx');
  assert.equal(webUrl('  http://192.168.10.80:8000/ '), 'http://192.168.10.80:8000/');
  assert.equal(webUrl('HTTPS://x.in'), 'HTTPS://x.in');
  assert.equal(webUrl(''), '');
  assert.equal(webUrl(null), '');
});

test('host of a url, lower-cased', () => {
  assert.equal(webHost('https://SivaMuruganErode.retailorders.in/ro14.html#/login'), 'sivamuruganerode.retailorders.in');
  assert.equal(webHost('not a url'), '');
});

test('merging sites skips repeats and names by host', () => {
  let n = 0;
  const id = () => `id${n += 1}`;
  const start = [{ id: 'a', name: 'Aosta', url: 'https://erd.puranisupplies.com/login.aspx' }];
  const out = webMergeSites(start, [
    { name: 'Aosta again', url: 'https://erd.puranisupplies.com/login.aspx' },
    { name: '', url: 'kasiviswanathan.varthagamsoft.co.in' },
    { name: 'Wondersoft', url: 'https://sivamuruganerode.retailorders.in/ro14.html#/login' },
    { name: 'Wondersoft dup', url: 'https://sivamuruganerode.retailorders.in/ro14.html#/login' },
    { name: 'bad', url: '' },
  ], id);
  assert.deepEqual(out.map((s) => s.name), ['Aosta', 'kasiviswanathan.varthagamsoft.co.in', 'Wondersoft']);
  assert.equal(out[1].url, 'https://kasiviswanathan.varthagamsoft.co.in');
  assert.deepEqual(out.slice(1).map((s) => s.id), ['id1', 'id2']);
  assert.equal(webMergeSites(null, null, id).length, 0);
});

test('moving a site keeps the others in order', () => {
  const sites = [{ id: 'a' }, { id: 'b' }, { id: 'c' }];
  assert.deepEqual(webMoveSite(sites, 'c', -1).map((s) => s.id), ['a', 'c', 'b']);
  assert.deepEqual(webMoveSite(sites, 'a', -1).map((s) => s.id), ['a', 'b', 'c']);
  assert.deepEqual(webMoveSite(sites, 'z', 1), sites);
});

test('HO portals become bar entries apart from the PC sites', () => {
  const sites = webPortalSites([{ portal_id: 7, name: 'Aosta', url: 'https://erd.puranisupplies.com/' }]);
  assert.deepEqual(sites.map((s) => [s.id, s.name, s.portal.portal_id]), [['p7', 'Aosta', 7]]);
  assert.deepEqual(webPortalSites(null), []);
});

test('the picked supplier finds its linked portal by any member code', () => {
  const portals = [
    { portal_id: 1, supplier_code: '' },
    { portal_id: 2, supplier_code: '107,109' },
    { portal_id: 3, supplier_code: '109' },
  ];
  assert.equal(webPortalFor(portals, '107').portal_id, 2);
  assert.equal(webPortalFor(portals, '108, 109').portal_id, 2);
  assert.equal(webPortalFor(portals, '200'), null);
  assert.equal(webPortalFor(portals, ''), null);
  assert.equal(webPortalFor(null, '107'), null);
});

test('supplier picker text resolves back to the supplier', () => {
  const suppliers = [{ supplier_code: '107,109', supplier_name: 'PURANI HOSPITAL SUPPLIES ' }, { supplier_code: '5', supplier_name: 'KASI' }];
  assert.equal(webSupplierOption(suppliers[0]), 'PURANI HOSPITAL SUPPLIES · 107,109');
  assert.equal(webFindSupplier(suppliers, ' KASI · 5 ').supplier_code, '5');
  assert.equal(webFindSupplier(suppliers, 'KASI'), null);
});

test('HO login shape never carries a password', () => {
  assert.deepEqual(webLogin({ username: 'u', has_password: 1, auto_submit: 0, password: 'x' }), { username: 'u', hasPassword: true, autoSubmit: false });
  assert.equal(webLogin(null), null);
});
