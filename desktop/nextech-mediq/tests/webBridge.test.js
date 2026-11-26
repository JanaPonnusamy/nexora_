import { test } from 'node:test';
import assert from 'node:assert/strict';
import { WEB_PAGE_IDS } from '../src/bridge/webPages.js';
import { toWebUser } from '../src/bridge/webUser.js';

test('embedded web pages include Quick Stock and Device Control as separate screens', () => {
  assert.ok(WEB_PAGE_IDS.includes('quick-stock'));
  assert.ok(WEB_PAGE_IDS.includes('device-control'));
  assert.ok(WEB_PAGE_IDS.includes('stock-check'));
  assert.notEqual(WEB_PAGE_IDS.indexOf('quick-stock'), WEB_PAGE_IDS.indexOf('device-control'));
});

test('web user mapping keeps platform and role fields the pages already read', () => {
  const user = toWebUser({
    user_id: 'u1',
    username: 'ops',
    first_name: 'Asha',
    is_platform_user: true,
    tenant_id: 't-home',
    roles: [{ role_name: 'SUPER_ADMIN', store_id: 's1', store_code: 'NMW' }],
  }, { tenantId: 't-selected', storeId: 's9' });
  assert.equal(user.id, 'u1');
  assert.equal(user.fullName, 'Asha');
  assert.equal(user.isPlatformUser, true);
  assert.deepEqual(user.roleNames, ['SUPER_ADMIN']);
  assert.equal(user.tenant, 't-selected');
  assert.equal(user.storeCode, 'NMW');
});
