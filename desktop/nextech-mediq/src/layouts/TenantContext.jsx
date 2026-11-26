import React from 'react';
import { Icon } from '../ui/icons.jsx';
import { GlassDropdown } from '../ui/glass.jsx';
import { useAuth } from '../contexts/AuthContext.jsx';
import { storesForTenant } from '../services/workspaceSelection.js';

export function TenantContext() {
  const {
    tenantId,
    storeId,
    tenants,
    stores,
    directoryError,
    directoryLoading,
    changeTenant,
    changeStore,
  } = useAuth();
  const tenantStores = storesForTenant(stores, tenantId);
  const tenantName = tenants.find((tenant) => String(tenant.tenant_id) === String(tenantId))?.tenant_name;
  const storeName = tenantStores.find((store) => String(store.store_id) === String(storeId))?.store_name;
  const canSwitchTenant = !directoryLoading && tenants.length > 1;
  const canSwitchStore = !directoryLoading && tenantStores.length > 1;
  const switchable = canSwitchTenant || canSwitchStore;

  const label = (
    <span className="ntm-tenant-trigger">
      <Icon name="store" size={15} />
      <span className="ntm-tenant-trigger__name">{storeName || (storeId ? 'Saved store' : 'No store')}</span>
      {switchable ? <Icon name="chevron" size={13} /> : null}
    </span>
  );

  if (!switchable) {
    return (
      <div className="ntm-tenant-trigger ntm-tenant-trigger--static" title={directoryError ? 'Tenant list unavailable' : tenantName || ''}>
        <Icon name="store" size={15} />
        <span className="ntm-tenant-trigger__name">{storeName || (storeId ? 'Saved store' : 'No store')}</span>
      </div>
    );
  }

  return (
    <GlassDropdown label={label}>
      <div className="ntm-tenant-menu" role="group" aria-label="Tenant and store">
        {canSwitchTenant ? (
          <label className="ntm-tenant-menu__field">
            <span>Tenant</span>
            <select aria-label="Tenant" value={tenantId} onChange={(event) => changeTenant(event.target.value)}>
              {tenants.map((tenant) => (
                <option key={tenant.tenant_id} value={tenant.tenant_id}>
                  {tenant.tenant_name || tenant.tenant_code || 'Tenant'}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <div className="ntm-tenant-menu__static">{tenantName || 'Tenant'}</div>
        )}
        {canSwitchStore ? (
          <label className="ntm-tenant-menu__field">
            <span>Store</span>
            <select aria-label="Store" value={storeId} onChange={(event) => changeStore(event.target.value)}>
              {tenantStores.map((store) => (
                <option key={store.store_id} value={store.store_id}>
                  {store.store_name || store.store_code || 'Store'}
                </option>
              ))}
            </select>
          </label>
        ) : null}
      </div>
    </GlassDropdown>
  );
}
