import assert from 'node:assert/strict';
import { test } from 'node:test';
import { harvestRow, pageResults, siteBestByCode, siteBestMatch, siteCounts, siteDecide, siteInCart, siteKind, siteMatchScore, siteOffer, siteQuery, siteScript, siteStock, siteTokens } from './siteCheck.js';

test('product names reduce to brand, strength and the rest', () => {
  assert.deepEqual(siteTokens("DOLO 650MG TAB 15'S"), ['DOLO', '650']);
  assert.deepEqual(siteTokens("BECOSULES CAP 20'S"), ['BECOSULES']);
  assert.deepEqual(siteTokens('MONTAIR LC TAB 10S'), ['MONTAIR', 'LC']);
  assert.deepEqual(siteTokens('Dolo-650 Tablet'), ['DOLO', '650']);
  assert.deepEqual(siteTokens('TAB. SHELCAL 500'), ['SHELCAL', '500']);
  assert.deepEqual(siteTokens('ATORVA 2.5 MG'), ['ATORVA', '2.5']);
  assert.deepEqual(siteTokens(null), []);
});

test('match needs the same brand and never another strength', () => {
  assert.ok(siteMatchScore("DOLO 650MG TAB 15'S", 'DOLO 650 TABLET') >= 0.6);
  assert.equal(siteMatchScore('DOLO 1000 TAB', 'DOLO 650 TAB'), 0);
  assert.equal(siteMatchScore('PAN 40 TAB', 'PANTOP 40 TAB'), 0);
  assert.equal(siteMatchScore('AUGMENTIN 625 DUO', 'AUGMENTIN 625 DUO TAB'), 1);
  assert.equal(siteMatchScore("XEPAN 40MG TAB 10'S", 'XEPAN 40MG INJ'), 0);
  assert.equal(siteMatchScore("XEPAN 40MG TAB 10'S", 'XEPAN 40MG TAB'), 1);
  assert.equal(siteMatchScore("BECOSULES CAP 20'S", 'BECOSULES CAPSULE'), 1);
  assert.equal(siteMatchScore("DOLO 650MG TAB 15'S", 'DOLO 650 SUSPENSION 60ML'), 0);
});

test('best match picks the closest row above the bar', () => {
  const rows = [{ n: 1, name: 'DOLO 650 SUSP 60ML' }, { n: 2, name: 'DOLO 650 TABLET' }, { n: 3, name: 'DOLOPAR 650' }];
  assert.equal(siteBestMatch("XEPAN 40MG TAB 10'S", [{ n: 1, name: 'XEPAN 40MG INJ' }, { n: 2, name: 'XEPAN 40MG TAB' }]).row.n, 2);
  assert.equal(siteBestMatch("DOLO 650MG TAB 15'S", rows).row.n, 2);
  assert.equal(siteBestMatch('CROCIN 500', rows), null);
  assert.equal(siteBestMatch('X', null), null);
});

test('stock text becomes a number', () => {
  assert.equal(siteStock('1,250'), 1250);
  assert.equal(siteStock('Stock: 40 strips'), 40);
  assert.equal(siteStock('Out of Stock'), 0);
  assert.equal(siteStock('Available'), Infinity);
  assert.equal(siteStock('—'), null);
  assert.equal(siteStock(''), null);
});

test('decision per product', () => {
  const at = (stock) => ({ row: { n: 1, name: 'X', stock } });
  assert.equal(siteDecide(10, at('120')).state, 'cart');
  assert.equal(siteDecide(10, at('Available')).state, 'cart');
  assert.deepEqual(siteDecide(10, at('4')), { state: 'partial', note: 'Only 4 in stock' });
  assert.equal(siteDecide(10, at('0')).state, 'none');
  assert.equal(siteDecide(10, at('')).state, 'check');
  assert.equal(siteDecide(10, null).state, 'none');
});

test('counts leave undecided rows as left', () => {
  const rows = [{ key: 'a' }, { key: 'b' }, { key: 'c' }, { key: 'd' }];
  const marks = { a: { state: 'cart' }, b: { state: 'none' }, c: { state: 'searching' }, d: { state: 'available' } };
  assert.deepEqual(siteCounts(rows, marks), { cart: 1, available: 1, none: 1, partial: 0, check: 0, left: 1 });
});

test('page functions travel as self-contained code', () => {
  const code = siteScript(pageResults);
  assert.match(code, /^\(function pageResults\(\) \{/);
  assert.equal(siteScript((a, b) => a + b, 'x', 2).endsWith('("x", 2)'), true);
});

test('site search text is brand + strength', () => {
  assert.equal(siteQuery("DOLO 650MG TAB 15'S"), 'DOLO 650');
  assert.equal(siteQuery("AUGMENTIN 625 DUO TAB 10'S"), 'AUGMENTIN 625');
  assert.equal(siteQuery("BECOSULES CAP 20'S"), 'BECOSULES');
  assert.equal(siteQuery('  '), '');
});

test('offer and site kind', () => {
  assert.equal(siteOffer('DOLOFORCE DT TAB Stock : 180 10\'S MANKIND PHARMA PVT LTD 11+1 72.19'), '11+1');
  assert.equal(siteOffer('DOLOKIND GEL Stock : 0'), '');
  assert.equal(siteKind('https://sivamuruganerode.retailorders.in/ro14.html#/nav/titlecard/prodadd'), 'retailorders');
  assert.equal(siteKind('http://127.0.0.1:8766/'), 'generic');
  assert.equal(siteKind('nonsense'), 'generic');
});

test('a product already in the cart is recognised by its site name', () => {
  const lines = ["3 TETRASYS LIFE SCIENCES SIVAMURUGAN MEDICAL AGENCY SYSPAN 40MG TAB 10'S 0 55.20 0.00 % 69.00 173.88"];
  assert.equal(siteInCart(lines, 'SYSPAN 40MG TAB'), true);
  assert.equal(siteInCart(lines, '.syspan  40mg tab'), true);
  assert.equal(siteInCart(lines, 'PANCIRA 40MG TAB'), false);
  assert.equal(siteInCart(null, 'SYSPAN'), false);
  assert.equal(siteInCart(lines, ''), false);
});

test('a code search is trusted only on exactly one result', () => {
  assert.equal(siteBestByCode([{ n: 1, name: 'DOLO 650 TABLET' }]).row.n, 1);
  assert.equal(siteBestByCode([{ n: 1, name: 'DOLO 650' }, { n: 2, name: 'DOLO 650 SUSP' }]), null);
  assert.equal(siteBestByCode([]), null);
  assert.equal(siteBestByCode(null), null);
});

test('harvest row keeps a product code when the site shows one', () => {
  const withCode = harvestRow({ name: 'DOLO 650', info: 'DOLO 650 Code: AB123 Stock : 40 (72.19)' });
  assert.equal(withCode.code, 'AB123');
  assert.equal(withCode.ptr, 72.19);
  const noCode = harvestRow({ name: 'DOLO 650', info: 'DOLO 650 Stock : 40' });
  assert.equal(noCode.code, '');
});
