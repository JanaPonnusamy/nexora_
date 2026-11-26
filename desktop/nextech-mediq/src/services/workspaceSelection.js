// Tenant and store selection. Ids are taken from the login user or from
// GET /api/tenants and GET /api/stores. The renderer never invents an id.
// Saving one here does not authorize it: the API's assert_tenant_access
// still rejects a tenant the caller cannot use.

export function workspaceFromLogin(settings, user) {
  const primary = user?.roles?.[0] || {};
  return {
    tenantId: settings?.tenantId || user?.tenant_id || '',
    storeId: settings?.storeId || primary.store_id || '',
    storeName: settings?.storeName || primary.store_name || '',
  };
}

export function storesForTenant(stores, tenantId) {
  if (!tenantId) return [];
  return (stores || []).filter(
    (store) => store && store.is_active !== false && String(store.tenant_id) === String(tenantId)
  );
}

export function selectTenant(current, tenantId, stores) {
  const scoped = storesForTenant(stores, tenantId);
  const keep = scoped.find((store) => String(store.store_id) === String(current?.storeId || ''));
  const next = keep || scoped[0] || null;
  return {
    tenantId: tenantId || '',
    storeId: next?.store_id || '',
    storeName: next?.store_name || '',
  };
}

export function selectStore(current, store) {
  if (!store) {
    return {
      tenantId: current?.tenantId || '',
      storeId: '',
      storeName: '',
    };
  }
  return {
    tenantId: store.tenant_id || current?.tenantId || '',
    storeId: store.store_id || '',
    storeName: store.store_name || '',
  };
}

// After the directory loads, drop a saved tenant the server did not return
// and fill an empty store from that tenant's own store list.
export function reconcileWorkspace(current, user, tenants, stores) {
  const tenantRows = (tenants || []).filter((tenant) => tenant && tenant.is_active !== false);
  if (!tenantRows.length) return { ...current };
  const allowed = new Set(tenantRows.map((tenant) => String(tenant.tenant_id)));
  let tenantId = current?.tenantId || '';
  if (!allowed.has(String(tenantId))) {
    const own = user?.tenant_id && allowed.has(String(user.tenant_id)) ? user.tenant_id : '';
    tenantId = own || tenantRows[0].tenant_id;
  }
  return selectTenant({ ...current, tenantId }, tenantId, stores);
}
