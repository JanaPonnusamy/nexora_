import { Fragment, useEffect, useMemo, useRef, useState } from 'react';
import { QueryClient, QueryClientProvider, useQuery, useQueryClient } from '@tanstack/react-query';
import { useVirtualizer } from '@tanstack/react-virtual';
import { api } from './api/client.js';
import {
  clearSession,
  loadSession,
  loadSettings,
  saveSession,
  saveSettings
} from './state/session.js';
import { buildBrandKey, buildPrefixSearchKey, normalizeForBadge, normalizeForLooseExact } from './lib/similarSearch.js';
import { getCachedProducts, syncCachedProducts } from './lib/productCache.js';

const screens = [
  { id: 'stock', label: 'Stock Availability', module: 'stock_availability' },
  { id: 'analysis', label: 'Supplier Stock Analysis', module: 'supplier_stock_analysis' },
  { id: 'nmw_sales', label: 'NMW Sales Report', module: 'nmw_sales_report' },
  { id: 'settings', label: 'Settings', module: 'settings' }
];

function asArray(value) {
  if (Array.isArray(value)) return value;
  if (Array.isArray(value?.items)) return value.items;
  if (Array.isArray(value?.suppliers)) return value.suppliers;
  if (Array.isArray(value?.data)) return value.data;
  return [];
}

function userModules(user) {
  const direct = user?.modules || user?.permissions || user?.allowedModules || [];
  return direct.map((item) => (typeof item === 'string' ? item : item?.module || item?.name)).filter(Boolean);
}

function canViewPurchaseDetails(session) {
  const roles = session?.user?.roles || [];
  const roleNames = roles.map((role) => String(role?.role_name || role?.role || '').toLowerCase());
  return roleNames.some((name) => name.includes('purchase'));
}

function isSalesmanOnly(session) {
  const roles = session?.user?.roles || [];
  const roleNames = roles.map((role) => String(role?.role_name || role?.role || '').toLowerCase());
  if (!roleNames.length) return false;
  return roleNames.every((name) => name.includes('salesman') || name.includes('sales man'));
}

// Mirrors backend dependencies.store_scope.is_supplier_analysis_blocked:
// Supplier Stock Analysis is admin-tier only - a login whose roles are ALL
// purchase-manager and/or salesman must not see the tab at all.
function isSupplierAnalysisBlocked(session) {
  const roles = session?.user?.roles || [];
  const roleNames = roles.map((role) => String(role?.role_name || role?.role || '').toLowerCase());
  if (!roleNames.length) return false;
  return roleNames.every((name) => name.includes('purchase') || name.includes('salesman') || name.includes('sales man'));
}

function isSuperAdmin(session) {
  // Mirrors backend dependencies.auth.has_full_access: a platform user (no
  // store-scoped role at all, e.g. superadmin with tenant_id=NULL) is always
  // full-access. Role names are also compared with separators stripped so
  // 'SUPER_ADMIN', 'Super Admin', and 'superadmin' all match — a plain
  // includes('super admin') missed the underscore variant used by this seed.
  if (session?.user?.is_platform_user) return true;
  const roles = session?.user?.roles || [];
  const roleNames = roles.map((role) => String(role?.role_name || role?.role || '').toLowerCase().replace(/[^a-z]/g, ''));
  return roleNames.some((name) => name.includes('superadmin') || name.includes('platformowner'));
}

function canUnlockDeviceSetup(userOrSession) {
  const roles = userOrSession?.user?.roles || userOrSession?.roles || [];
  const roleNames = roles.map((role) => String(role?.role_name || role?.role || '').toLowerCase());
  return roleNames.some((name) => (
    name.includes('admin')
    || name.includes('purchase_manager')
    || name.includes('purchase manager')
    || name.includes('platform_owner')
    || name.includes('platform owner')
  ));
}

function isWarehouseStore(store) {
  return String(store?.store_code || '').trim().toUpperCase() === 'NMW';
}

// Field-level visibility tier for Purchase/Billing History: NONE hides the
// section entirely, SUMMARY shows abbreviated/derived figures only, FULL
// shows every field (supplier name, PTR, customer, salesman...).
function historyVisibility(session) {
  if (isSalesmanOnly(session)) return 'NONE';
  if (isSuperAdmin(session) || canViewPurchaseDetails(session)) return 'FULL';
  return 'SUMMARY';
}

function abbreviateSupplierName(name, maxLength = 10) {
  const value = String(name || '').trim();
  if (!value) return '-';
  return value.length > maxLength ? `${value.slice(0, maxLength)}...` : value;
}

function formatMoney(value) {
  const num = Number(value);
  return Number.isFinite(num) ? num.toFixed(2) : '-';
}

function formatQty(value) {
  const num = Number(value);
  return Number.isFinite(num) ? String(num) : (value ?? '-');
}

// Shared across the whole desktop client so re-opening a previously viewed
// product (req 8) is instant even after switching screens.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 8 * 60 * 1000,
      gcTime: 15 * 60 * 1000,
      retry: 1,
      refetchOnWindowFocus: false
    }
  }
});

const PREFETCH_PREVIOUS_ROWS = 20;
const PREFETCH_NEXT_ROWS = 20;
const PREFETCH_CONCURRENCY = 4;
const RECENT_ANALYSIS_ROWS = 20;

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppShell />
    </QueryClientProvider>
  );
}

function AppShell() {
  const [settings, setSettings] = useState(loadSettings);
  const [session, setSession] = useState(loadSession);
  const [activeScreen, setActiveScreen] = useState('stock');
  // Tenant list for the super-admin tenant filter on the Stock Availability
  // screen. The API already scopes this to the caller's own tenant for any
  // non-super-admin login (see backend/controllers/tenant_controller.py), so
  // this array is a single item for everyone except a super admin / platform
  // user - it doubles as that role check for the UI without duplicating the
  // server's role logic here.
  const [tenants, setTenants] = useState([]);

  useEffect(() => {
    if (!session) { setTenants([]); return; }
    api.listTenants(session).then((rows) => setTenants(asArray(rows).filter((t) => t.is_active))).catch(() => {});
  }, [session]);

  const sessionStore = session?.user?.roles?.[0] || null;
  const effectiveTenantId = settings.tenantId || session?.user?.tenant_id || '';
  const effectiveStoreId = settings.storeId || sessionStore?.store_id || '';
  const effectiveStoreName = settings.storeName || sessionStore?.store_name || '';
  const runtimeSettings = {
    ...settings,
    tenantId: effectiveTenantId,
    storeId: effectiveStoreId,
    storeName: effectiveStoreName
  };
  const isConfigured = Boolean(effectiveTenantId && effectiveStoreId);

  const navItems = useMemo(() => {
    const modules = userModules(session?.user);
    // Supplier Stock Analysis is admin-tier only - a purchase-manager-only or
    // salesman-only login must not see the tab at all (the API also 403s it
    // server-side, this just keeps the nav honest). Checked before the
    // module-grant early-return below so it also applies to logins with no
    // module list.
    const base = isSupplierAnalysisBlocked(session) ? screens.filter((s) => s.id !== 'analysis') : screens;
    if (!modules.length) return base;
    // 'settings' and 'nmw_sales' are always available: the NMW Sales Report is
    // scoped server-side (store users see only their own approved bills), so it
    // never depends on a per-user module grant.
    const always = new Set(['settings', 'nmw_sales']);
    return base.filter((screen) => always.has(screen.id) || modules.includes(screen.module) || modules.includes(screen.id));
  }, [session]);

  useEffect(() => {
    if (!session && !isConfigured) {
      setActiveScreen('settings');
      return;
    }
    if (!navItems.some((item) => item.id === activeScreen)) {
      setActiveScreen(navItems[0]?.id || 'settings');
    }
  }, [activeScreen, navItems, isConfigured, session]);

  useEffect(() => {
    const storeName = session?.user?.roles?.[0]?.store_name || settings.storeName;
    document.title = storeName ? `Nexora Supplier Stock · ${storeName}` : 'Nexora Supplier Stock';
  }, [session, settings.storeName]);

  function persistSettings(next) {
    setSettings(saveSettings(next));
  }

  function handleLogin(loginPayload) {
    const savedSession = saveSession(loginPayload);
    const user = savedSession?.user || {};
    const primaryRole = user?.roles?.[0] || {};
    const nextSettings = saveSettings({
      ...loadSettings(),
      tenantId: loadSettings().tenantId || user?.tenant_id || '',
      storeId: loadSettings().storeId || primaryRole?.store_id || '',
      storeName: loadSettings().storeName || primaryRole?.store_name || ''
    });
    setSettings(nextSettings);
    setSession(savedSession);
    setActiveScreen('stock');
  }

  function handleLogout() {
    clearSession();
    setSession(null);
  }

  useEffect(() => {
    const onUnauthorized = () => handleLogout();
    window.addEventListener('nexora:unauthorized', onUnauthorized);
    return () => window.removeEventListener('nexora:unauthorized', onUnauthorized);
  }, []);

  useEffect(() => {
    if (!session) return;
    if (settings.tenantId && settings.storeId && settings.storeName) return;
    const user = session.user || {};
    const primaryRole = user?.roles?.[0] || {};
    const nextTenantId = settings.tenantId || user?.tenant_id || '';
    const nextStoreId = settings.storeId || primaryRole?.store_id || '';
    const nextStoreName = settings.storeName || primaryRole?.store_name || '';
    // Only persist when something actually resolved. A platform user (super
    // admin) has no tenant_id/store, so these stay unchanged — without this
    // equality guard the effect re-ran on its own setState forever (the
    // "Maximum update depth exceeded" storm).
    if (nextTenantId === settings.tenantId && nextStoreId === settings.storeId && nextStoreName === settings.storeName) return;
    setSettings(saveSettings({ ...settings, tenantId: nextTenantId, storeId: nextStoreId, storeName: nextStoreName }));
  }, [session, settings]);

  // A platform user (e.g. super admin) has no tenant_id, so on such a login the
  // API calls would drop the required tenant_id param and every request 422s.
  // Resolve the tenant from the device's registered store (or the first store
  // in this single-tenant deployment) and persist it so all screens can load.
  useEffect(() => {
    if (!session || settings.tenantId) return;
    api.listStores(session).then((rows) => {
      const stores = asArray(rows);
      const mine = stores.find((s) => s.store_id === effectiveStoreId)
        || stores.find(isWarehouseStore)
        || stores[0];
      if (mine?.tenant_id) {
        persistSettings({ ...settings, tenantId: mine.tenant_id });
      }
    }).catch(() => {});
  }, [session, settings.tenantId, effectiveStoreId]);

  return (
    <div className="app-shell">
      <header className="menubar">
        <div className="brand-block">
          <div className="brand-mark">N</div>
          <div>
            <h1>Nexora</h1>
            <p>Supplier Stock Client</p>
          </div>
        </div>

        <nav className="menubar-nav">
          {navItems.map((screen) => (
            <button
              key={screen.id}
              className={activeScreen === screen.id ? 'active' : ''}
              onClick={() => setActiveScreen(screen.id)}
            >
              {screen.label}
            </button>
          ))}
        </nav>

        <div className="menubar-right">
          {session ? (
            <div className="user-panel">
              <span>{session.user?.name || session.user?.username || 'Signed in user'}</span>
              <strong>{session.user?.roles?.[0]?.role_name || session.user?.role || session.user?.roleName || 'Role pending'}</strong>
            </div>
          ) : (
            <div className="user-panel muted">Sign in to unlock modules</div>
          )}

          {session && (
            <button className="ghost-button" onClick={handleLogout}>Sign out</button>
          )}
        </div>
      </header>

      <main className="workspace">
        {!session ? (
          <LoginScreen onLogin={handleLogin} onOpenSettings={() => setActiveScreen('settings')} />
        ) : !isConfigured && activeScreen === 'settings' ? (
          <SettingsScreen
            settings={runtimeSettings}
            onSave={persistSettings}
            requireAdminGate={!canUnlockDeviceSetup(session)}
            session={session}
          />
        ) : activeScreen === 'settings' ? (
          <SettingsScreen settings={runtimeSettings} onSave={persistSettings} session={session} />
        ) : activeScreen === 'analysis' ? (
          <SupplierStockAnalysis
            session={session}
            settings={runtimeSettings}
            tenants={tenants}
            onTenantChange={(tenantId) => persistSettings({ ...settings, tenantId })}
          />
        ) : activeScreen === 'nmw_sales' ? (
          <NmwSalesReport session={session} settings={runtimeSettings} />
        ) : (
          <StockAvailability
            session={session}
            settings={runtimeSettings}
            onOpenSettings={() => setActiveScreen('settings')}
            tenants={tenants}
            onTenantChange={(tenantId) => persistSettings({ ...settings, tenantId })}
          />
        )}
      </main>
    </div>
  );
}


function SettingsScreen({ settings, onSave, requireAdminGate = false, session = null }) {
  const [draft, setDraft] = useState(settings);
  const [status, setStatus] = useState({ state: 'idle', message: '' });
  const [tenants, setTenants] = useState([]);
  const [stores, setStores] = useState([]);
  const [devices, setDevices] = useState([]);
  const [waState, setWaState] = useState(null);
  const [waStatus, setWaStatus] = useState({ state: 'idle', message: '' });
  const [waDraft, setWaDraft] = useState({ browser_command: '', delivery_mode: 'manual_browser', launch_wait_seconds: 15 });
  const [waProfileDraft, setWaProfileDraft] = useState({
    profile_id: '',
    profile_name: '',
    owner_type: 'store',
    owner_name: '',
    tenant_id: '',
    store_id: '',
    default_phone: '',
    notes: '',
    is_default: false
  });
  const [adminUnlocked, setAdminUnlocked] = useState(!requireAdminGate);
  const [adminForm, setAdminForm] = useState({ username: '', password: '' });
  const [adminStatus, setAdminStatus] = useState({ state: 'idle', message: '' });
  const [adminSession, setAdminSession] = useState(null);
  const effectiveSession = session || adminSession;

  useEffect(() => setDraft(settings), [settings]);
  useEffect(() => {
    if (!effectiveSession) return;
    loadWhatsApp();
  }, [effectiveSession]);

  async function unlockAdmin(event) {
    event.preventDefault();
    setAdminStatus({ state: 'loading', message: 'Checking admin credentials...' });
    try {
      const response = await api.login(adminForm);
      const user = response.user || response.data?.user || response;
      if (!canUnlockDeviceSetup(user)) {
        setAdminStatus({ state: 'error', message: 'This account is authenticated, but it does not have setup access.' });
        return;
      }
      setAdminSession(response);
      setAdminUnlocked(true);
      setAdminStatus({ state: 'ok', message: `Signed in as ${user?.name || user?.username || 'admin'}.` });
    } catch (error) {
      setAdminStatus({ state: 'error', message: error.message });
    }
  }

  if (requireAdminGate && !adminUnlocked) {
    return (
      <section className="screen-panel">
        <ScreenHeader title="Device Setup" subtitle="This device isn't registered to a store yet. Sign in with an admin account to configure it." />
        <form className="login-form" onSubmit={unlockAdmin}>
          <label>
            Admin username
            <input value={adminForm.username} onChange={(event) => setAdminForm({ ...adminForm, username: event.target.value })} />
          </label>
          <label>
            Admin password
            <input type="password" value={adminForm.password} onChange={(event) => setAdminForm({ ...adminForm, password: event.target.value })} />
          </label>
          <button className="primary-button" type="submit">Unlock configuration</button>
          {adminStatus.message && <span className={`status ${adminStatus.state}`}>{adminStatus.message}</span>}
        </form>
      </section>
    );
  }

  async function loadTenantStore() {
    setStatus({ state: 'loading', message: 'Loading tenant/store list...' });
    try {
      const [tenantRows, storeRows] = await Promise.all([api.listTenants(effectiveSession), api.listStores(effectiveSession)]);
      setTenants(asArray(tenantRows));
      setStores(asArray(storeRows));
      setStatus({ state: 'ok', message: 'Tenant/store list loaded.' });
    } catch (error) {
      setStatus({ state: 'error', message: error.message });
    }
  }

  async function requestActivation() {
    setStatus({ state: 'loading', message: 'Requesting device activation...' });
    try {
      const desktop = window.nexoraDesktop || {};
      const result = await api.requestActivation({
        device_fingerprint: desktop.fingerprint || `browser-${navigator.userAgent}`,
        machine_name: desktop.machineName || 'unknown-machine',
        app_version: '0.1.0',
        requested_store_name: draft.storeName,
        requested_store_code: draft.storeCode || '',
        install_code: ''
      }, effectiveSession);
      setStatus({ state: 'ok', message: `Activation requested. Client ID: ${result.client_id} (${result.status})` });
      setDraft({ ...draft, clientId: result.client_id });
    } catch (error) {
      setStatus({ state: 'error', message: error.message });
    }
  }

  async function loadDevices() {
    setStatus({ state: 'loading', message: 'Loading desktop devices...' });
    try {
      const result = await api.listDesktopDevices(effectiveSession);
      setDevices(result.devices || []);
      setStatus({ state: 'ok', message: 'Device list loaded.' });
    } catch (error) {
      setStatus({ state: 'error', message: error.message });
    }
  }

  async function approveDevice(clientId) {
    if (!draft.tenantId || !draft.storeId) {
      setStatus({ state: 'error', message: 'Tenant ID and Store ID are required before approval.' });
      return;
    }
    setStatus({ state: 'loading', message: 'Approving device...' });
    try {
      await api.approveDesktopDevice(clientId, {
        tenant_id: draft.tenantId,
        store_id: draft.storeId,
        store_code: draft.storeCode || '',
        store_name: draft.storeName || '',
        server_base_url: draft.apiBaseUrl,
        enabled: true
      }, effectiveSession);
      await loadDevices();
      setStatus({ state: 'ok', message: 'Device approved.' });
    } catch (error) {
      setStatus({ state: 'error', message: error.message });
    }
  }

  function orderedStoreList() {
    const order = draft.storeOrder || [];
    const rank = new Map(order.map((storeId, index) => [storeId, index]));
    return [...stores].sort((a, b) => {
      const rankA = rank.has(a.store_id) ? rank.get(a.store_id) : Infinity;
      const rankB = rank.has(b.store_id) ? rank.get(b.store_id) : Infinity;
      if (rankA !== rankB) return rankA - rankB;
      return String(a.store_name || a.store_code || '').localeCompare(String(b.store_name || b.store_code || ''));
    });
  }

  function moveStore(storeId, direction) {
    const ordered = orderedStoreList().map((store) => store.store_id);
    const index = ordered.indexOf(storeId);
    const swapWith = index + direction;
    if (index < 0 || swapWith < 0 || swapWith >= ordered.length) return;
    [ordered[index], ordered[swapWith]] = [ordered[swapWith], ordered[index]];
    setDraft({ ...draft, storeOrder: ordered });
  }

  async function testConnection() {
    setStatus({ state: 'loading', message: 'Testing connection...' });
    try {
      const result = await api.testConnection(draft);
      setStatus({ state: 'ok', message: `Connected successfully (${result.status})` });
    } catch (error) {
      setStatus({ state: 'error', message: error.message });
    }
  }

  function hydrateWhatsApp(payload) {
    setWaState(payload);
    setWaDraft({
      browser_command: payload.settings?.browser_command || '',
      delivery_mode: payload.settings?.delivery_mode || 'manual_browser',
      launch_wait_seconds: payload.settings?.launch_wait_seconds || 15
    });
  }

  async function loadWhatsApp() {
    setWaStatus({ state: 'loading', message: 'Loading WhatsApp settings...' });
    try {
      const payload = await api.getWhatsAppState(effectiveSession);
      hydrateWhatsApp(payload);
      setWaStatus({ state: 'ok', message: 'WhatsApp settings loaded.' });
    } catch (error) {
      setWaStatus({ state: 'error', message: error.message });
    }
  }

  async function saveWhatsAppRuntime() {
    setWaStatus({ state: 'loading', message: 'Saving WhatsApp runtime...' });
    try {
      const payload = await api.saveWhatsAppSettings(waDraft, effectiveSession);
      hydrateWhatsApp(payload);
      setWaStatus({ state: 'ok', message: 'WhatsApp runtime settings saved.' });
    } catch (error) {
      setWaStatus({ state: 'error', message: error.message });
    }
  }

  async function saveWhatsAppProfile() {
    setWaStatus({ state: 'loading', message: 'Saving WhatsApp profile...' });
    try {
      const payload = await api.saveWhatsAppProfile(waProfileDraft, effectiveSession);
      setWaState((current) => current ? { ...current, profiles: payload.profiles, capabilities: payload.capabilities } : current);
      const profile = payload.profile || {};
      setWaProfileDraft({
        profile_id: profile.profile_id || '',
        profile_name: profile.profile_name || '',
        owner_type: profile.owner_type || 'store',
        owner_name: profile.owner_name || '',
        tenant_id: profile.tenant_id || '',
        store_id: profile.store_id || '',
        default_phone: profile.default_phone || '',
        notes: profile.notes || '',
        is_default: Boolean(profile.is_default)
      });
      setWaStatus({ state: 'ok', message: 'WhatsApp profile saved.' });
    } catch (error) {
      setWaStatus({ state: 'error', message: error.message });
    }
  }

  async function launchWhatsAppProfile(profileId) {
    setWaStatus({ state: 'loading', message: 'Opening WhatsApp Web...' });
    try {
      const payload = await api.launchWhatsAppProfile(profileId, effectiveSession);
      setWaStatus({ state: 'ok', message: payload.message || 'WhatsApp Web opened.' });
    } catch (error) {
      setWaStatus({ state: 'error', message: error.message });
    }
  }

  async function deleteWhatsAppProfile(profileId) {
    setWaStatus({ state: 'loading', message: 'Deleting WhatsApp profile...' });
    try {
      const payload = await api.deleteWhatsAppProfile(profileId, effectiveSession);
      setWaState((current) => current ? { ...current, profiles: payload.profiles, capabilities: payload.capabilities } : current);
      setWaProfileDraft({
        profile_id: '',
        profile_name: '',
        owner_type: 'store',
        owner_name: '',
        tenant_id: '',
        store_id: '',
        default_phone: '',
        notes: '',
        is_default: false
      });
      setWaStatus({ state: 'ok', message: 'WhatsApp profile deleted.' });
    } catch (error) {
      setWaStatus({ state: 'error', message: error.message });
    }
  }

  return (
    <section className="screen-panel">
      <ScreenHeader title="Settings" subtitle="Choose how this desktop client reaches the Nexora API." />
      <div className="form-grid">
        <label>
          Server mode
          <div className="segmented-control">
            {['LAN', 'Internet'].map((mode) => (
              <button
                key={mode}
                className={draft.serverMode === mode ? 'selected' : ''}
                onClick={() => setDraft({ ...draft, serverMode: mode })}
                type="button"
              >
                {mode}
              </button>
            ))}
          </div>
        </label>
        <label>
          API base URL
          <input value={draft.apiBaseUrl} onChange={(event) => setDraft({ ...draft, apiBaseUrl: event.target.value })} />
        </label>
        <label>
          Bootstrap URL
          <input value={draft.bootstrapUrl} onChange={(event) => setDraft({ ...draft, bootstrapUrl: event.target.value })} placeholder="Optional discovery URL" />
        </label>
        <label>
          Tenant ID
          <input value={draft.tenantId} onChange={(event) => setDraft({ ...draft, tenantId: event.target.value })} />
        </label>
        <label>
          Store ID
          <input value={draft.storeId} onChange={(event) => setDraft({ ...draft, storeId: event.target.value })} />
        </label>
        <label>
          Store Name
          <input value={draft.storeName} onChange={(event) => setDraft({ ...draft, storeName: event.target.value })} />
        </label>
      </div>
      <div className="action-row">
        <button className="primary-button" onClick={() => { onSave(draft); setStatus({ state: 'ok', message: 'Settings saved.' }); }}>Save settings</button>
        <button className="secondary-button" onClick={testConnection}>Test connection</button>
        <button className="secondary-button" onClick={loadTenantStore}>Load tenant/store</button>
        <button className="secondary-button" onClick={requestActivation}>Request activation</button>
        <button className="secondary-button" onClick={loadDevices}>Load devices</button>
        {status.message && <span className={`status ${status.state}`}>{status.message}</span>}
      </div>

      <div className="settings-grid">
        <DataTable
          status={{ state: 'idle', message: 'Tenants' }}
          columns={['Tenant', 'Name']}
          rows={tenants.map((tenant) => [tenant.tenant_id, tenant.tenant_name || tenant.tenant_code || '-'])}
        />
        <DataTable
          status={{ state: 'idle', message: 'Stores' }}
          columns={['Store ID', 'Code', 'Name']}
          rows={stores.map((store) => [store.store_id, store.store_code || '-', store.store_name || '-'])}
        />
      </div>

      <div className="table-wrap">
        <div className="status-line idle">
          Store display order. This client's registered store (Store ID above) always shows first; use the arrows to order the rest.
        </div>
        {stores.length ? (
          <table>
            <thead><tr><th>Order</th><th>Store</th><th>Move</th></tr></thead>
            <tbody>
              {orderedStoreList().map((store, index) => (
                <tr key={store.store_id}>
                  <td>{store.store_id === draft.storeId ? 'Pinned (this store)' : index + 1}</td>
                  <td>{store.store_name || store.store_code || store.store_id}</td>
                  <td>
                    <button
                      type="button"
                      className="secondary-button"
                      disabled={store.store_id === draft.storeId || index === 0}
                      onClick={() => moveStore(store.store_id, -1)}
                    >
                      Up
                    </button>
                    <button
                      type="button"
                      className="secondary-button"
                      disabled={store.store_id === draft.storeId || index === orderedStoreList().length - 1}
                      onClick={() => moveStore(store.store_id, 1)}
                    >
                      Down
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <div className="empty-state">Click "Load tenant/store" to load stores for ordering.</div>}
      </div>

      <div className="table-wrap">
        <div className="status-line idle">Desktop devices. Fill Tenant ID + Store ID above, then approve.</div>
        {devices.length ? (
          <table>
            <thead><tr><th>Client ID</th><th>Machine</th><th>Status</th><th>Requested Store</th><th>Action</th></tr></thead>
            <tbody>
              {devices.map((device) => (
                <tr key={device.client_id}>
                  <td>{device.client_id}</td>
                  <td>{device.machine_name || '-'}</td>
                  <td>{device.status}</td>
                  <td>{device.requested_store_name || device.store_name || '-'}</td>
                  <td><button className="secondary-button" onClick={() => approveDevice(device.client_id)}>Approve</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <div className="empty-state">No devices loaded.</div>}
      </div>

      <div className="table-wrap">
        <div className={`status-line ${waStatus.state}`}>{waStatus.message || 'WhatsApp settings and QR profiles.'}</div>
        <div className="form-grid">
          <label>
            WhatsApp browser
            <input value={waDraft.browser_command} onChange={(event) => setWaDraft({ ...waDraft, browser_command: event.target.value })} placeholder="C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" />
          </label>
          <label>
            Delivery mode
            <select value={waDraft.delivery_mode} onChange={(event) => setWaDraft({ ...waDraft, delivery_mode: event.target.value })}>
              <option value="manual_browser">Manual browser</option>
              <option value="selenium">Selenium automation</option>
            </select>
          </label>
          <label>
            Launch wait seconds
            <input type="number" min="10" value={waDraft.launch_wait_seconds} onChange={(event) => setWaDraft({ ...waDraft, launch_wait_seconds: Number(event.target.value || 15) })} />
          </label>
        </div>
        <div className="action-row">
          <button className="secondary-button" onClick={loadWhatsApp}>Refresh WhatsApp</button>
          <button className="primary-button" onClick={saveWhatsAppRuntime}>Save WhatsApp runtime</button>
        </div>

        <div className="form-grid">
          <label>
            Profile name
            <input value={waProfileDraft.profile_name} onChange={(event) => setWaProfileDraft({ ...waProfileDraft, profile_name: event.target.value })} />
          </label>
          <label>
            Owner type
            <select value={waProfileDraft.owner_type} onChange={(event) => setWaProfileDraft({ ...waProfileDraft, owner_type: event.target.value })}>
              <option value="store">Store</option>
              <option value="user">User</option>
              <option value="system">System</option>
            </select>
          </label>
          <label>
            Owner name
            <input value={waProfileDraft.owner_name} onChange={(event) => setWaProfileDraft({ ...waProfileDraft, owner_name: event.target.value })} />
          </label>
          <label>
            Default phone
            <input value={waProfileDraft.default_phone} onChange={(event) => setWaProfileDraft({ ...waProfileDraft, default_phone: event.target.value })} />
          </label>
        </div>
        <div className="action-row">
          <button className="primary-button" onClick={saveWhatsAppProfile}>{waProfileDraft.profile_id ? 'Update profile' : 'Create profile'}</button>
          <button className="secondary-button" onClick={() => setWaProfileDraft({ profile_id: '', profile_name: '', owner_type: 'store', owner_name: '', tenant_id: '', store_id: '', default_phone: '', notes: '', is_default: false })}>New profile</button>
        </div>

        {waState?.profiles?.length ? (
          <table>
            <thead><tr><th>Profile</th><th>Owner</th><th>Phone</th><th>Actions</th></tr></thead>
            <tbody>
              {waState.profiles.map((profile) => (
                <tr key={profile.profile_id}>
                  <td>{profile.profile_name}{profile.is_default ? ' (Default)' : ''}</td>
                  <td>{profile.owner_type}{profile.owner_name ? ` / ${profile.owner_name}` : ''}</td>
                  <td>{profile.default_phone || '-'}</td>
                  <td>
                    <button className="secondary-button" onClick={() => setWaProfileDraft({
                      profile_id: profile.profile_id,
                      profile_name: profile.profile_name,
                      owner_type: profile.owner_type,
                      owner_name: profile.owner_name,
                      tenant_id: profile.tenant_id,
                      store_id: profile.store_id,
                      default_phone: profile.default_phone,
                      notes: profile.notes,
                      is_default: Boolean(profile.is_default)
                    })}>Edit</button>
                    <button className="secondary-button" onClick={() => launchWhatsAppProfile(profile.profile_id)}>Launch QR</button>
                    <button className="secondary-button" onClick={() => deleteWhatsAppProfile(profile.profile_id)}>Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <div className="empty-state">No WhatsApp profiles created yet.</div>}
      </div>
    </section>
  );
}

function LoginScreen({ onLogin, onOpenSettings }) {
  const [form, setForm] = useState({ username: '', password: '' });
  const [status, setStatus] = useState({ state: 'idle', message: '' });

  async function submit(event) {
    event.preventDefault();
    setStatus({ state: 'loading', message: 'Signing in...' });
    try {
      const response = await api.login(form);
      const user = response.user || response.data?.user || response;
      onLogin({ ...response, user });
    } catch (error) {
      setStatus({ state: 'error', message: error.message });
    }
  }

  return (
    <section className="login-layout">
      <div className="login-copy">
        <span className="eyebrow">Nexora desktop</span>
        <h2>Supplier stock workbench</h2>
        <p>Use your Nexora credentials to open stock availability and supplier analysis modules.</p>
      </div>
      <form className="login-card" onSubmit={submit}>
        <label>
          Username
          <input autoFocus value={form.username} onChange={(event) => setForm({ ...form, username: event.target.value })} />
        </label>
        <label>
          Password
          <input type="password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} />
        </label>
        <button className="primary-button" type="submit">Sign in</button>
        <button className="link-button" type="button" onClick={onOpenSettings}>API settings</button>
        {status.message && <span className={`status ${status.state}`}>{status.message}</span>}
      </form>
    </section>
  );
}

function StockAvailability({ session, settings, onOpenSettings, tenants = [], onTenantChange }) {
  const [query, setQuery] = useState('');
  const [onlyStock, setOnlyStock] = useState(false);
  // Seed from the last successful store list so the NMW/store panels render
  // immediately on launch instead of sitting on placeholders while
  // api.listStores is in flight - listStores below still runs and replaces
  // this with the fresh list right after.
  const [allStores, setAllStores] = useState(() => {
    try { return JSON.parse(localStorage.getItem('nexora.desktop.storesCache') || '[]'); } catch { return []; }
  });
  const [searchStores, setSearchStores] = useState([]);
  const [storeDetails, setStoreDetails] = useState({});
  const [selectedStoreId, setSelectedStoreId] = useState(session?.user?.roles?.[0]?.store_id || '');
  const [hasSearched, setHasSearched] = useState(false);
  const [status, setStatus] = useState({ state: 'idle', message: 'Type product name to search.' });
  const [purchaseDetail, setPurchaseDetail] = useState(null);
  const [billDetail, setBillDetail] = useState(null);
  const [nonMovingProducts, setNonMovingProducts] = useState([]);
  const [nonMovingLoading, setNonMovingLoading] = useState(true);
  const [nonMovingIndex, setNonMovingIndex] = useState(0);
  const [nonMovingStoreFilter, setNonMovingStoreFilter] = useState('');
  const [isAutoQuery, setIsAutoQuery] = useState(false);
  const searchInputRef = useRef(null);

  const loginStoreId = session?.user?.roles?.[0]?.store_id || loadSettings().storeId;
  const visibility = historyVisibility(session);
  const canViewPurchase = visibility !== 'NONE';
  const hideSupplierColumn = isSalesmanOnly(session);
  const searchIdRef = useRef(0);
  // In-memory caches: instant re-render for anything already fetched this session.
  // searchCacheRef: normalized query -> stores[] from the search API.
  // detailCacheRef: "storeId:productCode" -> fully loaded store detail (incl. bill items).
  const searchCacheRef = useRef(new Map());
  const detailCacheRef = useRef(new Map());

  useEffect(() => {
    api.listStores(session).then((rows) => {
      const items = asArray(rows);
      setAllStores(items);
      try { localStorage.setItem('nexora.desktop.storesCache', JSON.stringify(items)); } catch { /* best effort */ }
    }).catch(() => {});
  }, [session]);

  useEffect(() => {
    // Guard on settings.tenantId too: for a platform user (e.g. super admin) it
    // resolves asynchronously (device has no configured tenant of its own), and
    // this effect only depends on [allStores] - without the guard+dependency it
    // would fire once with tenant_id missing (422 on every store) and never
    // retry once the tenant actually resolves.
    if (!allStores.length || !settings?.tenantId) return;
    Promise.all(allStores.map((store) => api.getNonMovingStock(store.store_id, session, { tenantId: settings.tenantId, dwellDays: 120, minPurAge: 10, limit: 50 })
      .then((result) => asArray(result?.rows)
        .map((row) => ({ ...row, __storeId: store.store_id, __storeName: store.store_name || store.store_code })))
      .catch(() => [])))
      .then((lists) => {
        const merged = lists.flat();
        merged.sort((a, b) => {
          const valueA = nonMovingCost(a);
          const valueB = nonMovingCost(b);
          return valueB - valueA;
        });
        setNonMovingProducts(merged);
        setNonMovingLoading(false);
      });
  }, [allStores, settings?.tenantId]);

  const filteredNonMoving = useMemo(
    () => (nonMovingStoreFilter
      ? nonMovingProducts.filter((row) => row.__storeId === nonMovingStoreFilter)
      : nonMovingProducts),
    [nonMovingProducts, nonMovingStoreFilter]
  );

  // Switching the store filter can leave the carousel pointing past the end
  // of the (now shorter) filtered list — snap back to the first item.
  useEffect(() => { setNonMovingIndex(0); }, [nonMovingStoreFilter]);

  useEffect(() => {
    if (filteredNonMoving.length < 2) return;
    const timer = setInterval(() => {
      setNonMovingIndex((index) => (index + 1) % filteredNonMoving.length);
    }, 6000);
    return () => clearInterval(timer);
  }, [filteredNonMoving]);

  function nonMovingStep(delta) {
    if (!filteredNonMoving.length) return;
    setNonMovingIndex((index) => (index + delta + filteredNonMoving.length) % filteredNonMoving.length);
  }

  useEffect(() => {
    if (isAutoQuery && searchInputRef.current) {
      searchInputRef.current.focus();
      searchInputRef.current.select();
    }
  }, [isAutoQuery]);

  useEffect(() => {
    const value = query.trim().replace(/\s+/g, ' ');
    if (value.length < 2) {
      searchIdRef.current += 1;
      setSearchStores([]);
      setStoreDetails({});
      setHasSearched(false);
      setStatus({ state: 'idle', message: 'Type at least 2 characters to search.' });
      return;
    }
    // Cached term: render instantly on every keystroke, no debounce needed.
    if (searchCacheRef.current.has(`${onlyStock ? '1' : '0'}|${value.toLowerCase()}`)) {
      runSearch(value);
      return;
    }
    const timer = setTimeout(() => runSearch(value), 150);
    return () => clearTimeout(timer);
  }, [query, onlyStock]);

  async function loadStoreCore(storeId, product) {
    const cacheKey = `${storeId}:${product.product_code}`;
    const cached = detailCacheRef.current.get(cacheKey);
    if (cached) return cached;

    // Single round trip per store (batches+purchases+sales+movement combined
    // server-side) instead of 4 separate HTTP/SP calls — cuts store load time.
    // months:4 so the trend chart can show 4 months (see MonthlyMovementChart).
    const result = await api.getStockCore(storeId, product.product_code, session, { months: 4 });
    const core = {
      product,
      batches: asArray(result?.batches),
      purchases: asArray(result?.purchases),
      sales: asArray(result?.sales),
      movement: asArray(result?.movement),
      billItems: []
    };
    // Only cache successful, non-empty fetches — a transient failure or an
    // empty result (e.g. SP not deployed yet) must not poison future searches.
    if (core.batches.length || core.purchases.length || core.sales.length || core.movement.length) {
      detailCacheRef.current.set(cacheKey, core);
    }
    return core;
  }

  function primeStoreCoreCache(items, productsByStore) {
    const seeded = {};
    asArray(items).forEach((item) => {
      const product = productsByStore.get(item.store_id);
      if (!product) return;
      const core = {
        product,
        batches: asArray(item?.batches),
        purchases: asArray(item?.purchases),
        sales: asArray(item?.sales),
        movement: asArray(item?.movement),
        billItems: asArray(item?.billItems),
        activeBillNo: item?.activeBillNo || null,
      };
      const cacheKey = `${item.store_id}:${product.product_code}`;
      if (core.batches.length || core.purchases.length || core.sales.length || core.movement.length || core.billItems.length) {
        detailCacheRef.current.set(cacheKey, core);
      }
      seeded[item.store_id] = core;
    });
    return seeded;
  }

  async function runSearch(value) {
    if (!value || value.length < 2) {
      searchIdRef.current += 1;
      setHasSearched(false);
      setStatus({ state: 'idle', message: 'Type at least 2 characters to search.' });
      return;
    }
    const searchId = ++searchIdRef.current;
    setHasSearched(true);
    const startedAt = performance.now();
    const cacheKey = `${onlyStock ? '1' : '0'}|${value.toLowerCase()}`;
    const cachedStores = searchCacheRef.current.get(cacheKey);

    try {
      let stores;
      if (cachedStores) {
        stores = cachedStores; // instant: skip the network round trip entirely
      } else {
        setStatus({ state: 'loading', message: 'Searching products...' });
        const response = await api.searchStockProducts(value, session, { onlyStock });
        if (searchIdRef.current !== searchId) return; // superseded by a newer search
        stores = asArray(response?.stores);
        searchCacheRef.current.set(cacheKey, stores);
      }

      setSearchStores(stores);
      const total = stores.reduce((sum, store) => sum + (store.products || []).length, 0);

      const storesWithProduct = stores.filter((store) => (store.products || [])[0]);
      if (!storesWithProduct.length) {
        setStoreDetails({});
        setStatus({ state: 'ok', message: total ? `${total} product match(es) found.` : 'No products matched in any store.' });
        return;
      }

      // Seed instantly from cache (if present) so already-seen products render
      // with zero delay, then only fetch what's actually missing.
      const seeded = {};
      const toFetch = [];
      storesWithProduct.forEach((store) => {
        const product = store.products[0];
        const cached = detailCacheRef.current.get(`${store.store_id}:${product.product_code}`);
        if (cached) seeded[store.store_id] = cached;
        else toFetch.push(store);
      });
      setStoreDetails(seeded);

      if (!toFetch.length) {
        const elapsedMs = Math.round(performance.now() - startedAt);
        setStatus({ state: 'ok', message: `${total} product match(es) found. All stores loaded in ${elapsedMs}ms (cached).` });
        return;
      }

      setStatus({ state: 'loading', message: `${total} product match(es) found. Loading ${toFetch.length} store(s)...` });

      const productsByStore = new Map(toFetch.map((store) => [store.store_id, store.products[0]]));
      try {
        const bulk = await api.getStockCoreBulk(
          toFetch.map((store) => ({
            store_id: store.store_id,
            product_code: store.products[0].product_code,
          })),
          session,
          { months: 4 }
        );
        if (searchIdRef.current !== searchId) return;
        const resolved = primeStoreCoreCache(bulk?.items, productsByStore);
        const misses = {};
        toFetch.forEach((store) => {
          if (!resolved[store.store_id]) misses[store.store_id] = null;
        });
        setStoreDetails((prev) => ({ ...prev, ...resolved, ...misses }));
        const elapsedMs = Math.round(performance.now() - startedAt);
        setStatus({ state: 'ok', message: `${total} product match(es) found. All stores loaded in ${elapsedMs}ms.` });
      } catch (bulkError) {
        // Fallback to the original per-store path if the bulk endpoint is not
        // deployed yet or one request fails unexpectedly.
        let settled = 0;
        toFetch.forEach((store) => {
          const product = store.products[0];
          loadStoreCore(store.store_id, product)
            .then((core) => {
              if (searchIdRef.current !== searchId) return;
              setStoreDetails((prev) => ({ ...prev, [store.store_id]: core }));
            })
            .catch(() => {
              if (searchIdRef.current !== searchId) return;
              setStoreDetails((prev) => ({ ...prev, [store.store_id]: null }));
            })
            .finally(() => {
              settled += 1;
              if (settled === toFetch.length && searchIdRef.current === searchId) {
                const elapsedMs = Math.round(performance.now() - startedAt);
                setStatus({ state: 'ok', message: `${total} product match(es) found. All stores loaded in ${elapsedMs}ms.` });
              }
            });
        });
      }
    } catch (error) {
      if (searchIdRef.current !== searchId) return;
      setSearchStores([]);
      setStoreDetails({});
      setStatus({ state: 'error', message: error.message });
    }
  }

  function handleProductSelect(storeId, product) {
    const searchId = searchIdRef.current;
    loadStoreCore(storeId, product)
      .then((core) => {
        if (searchIdRef.current !== searchId) return;
        setStoreDetails((prev) => ({ ...prev, [storeId]: core }));
      })
      .catch(() => {});
  }

  const searchProductsByStore = new Map(searchStores.map((store) => [store.store_id, store.products || []]));
  // allStores can still be loading when a search already resolved (its request
  // fired independently and can win the race) - fall back to the stores the
  // search itself returned so rows render immediately instead of showing
  // "no matching products" against placeholder store IDs the search can't match.
  const visibleStoresUnfiltered = allStores.length
    ? allStores
    : searchStores.length
      ? searchStores
      // The warehouse (NMW) row must exist in this placeholder set too, or
      // the whole NMW panel briefly vanishes during the initial store-list
      // load (isWarehouseStore finds nothing to pin until allStores resolves).
      : Array.from({ length: 5 }, (_, index) => (
        index === 0
          ? { store_id: 'pending-nmw', store_code: 'NMW', store_name: 'Loading warehouse...' }
          : { store_id: 'pending-' + index, store_name: 'Loading store...' }
      ));
  // A super admin's store list spans every tenant (the API only narrows this
  // to one tenant for non-broad roles) - without this filter their screen mixed
  // every tenant's branches into one grid. tenants.length > 1 is true only for
  // a broad login, since the API already locks everyone else to their own
  // tenant, so this filter is a no-op for regular store/purchase/salesman users.
  const visibleStores = tenants.length > 1 && settings?.tenantId
    ? visibleStoresUnfiltered.filter((store) => !store.tenant_id || store.tenant_id === settings.tenantId)
    : visibleStoresUnfiltered;
  const stores = orderStores(visibleStores, loginStoreId, settings?.storeOrder || []);
  const warehouseStore = stores.find(isWarehouseStore);
  const otherStores = stores.filter((store) => !isWarehouseStore(store));

  return (
    <section className="store-workbench">
      <div className="global-search-row">
        <input
          ref={searchInputRef}
          autoFocus
          className={isAutoQuery ? 'auto-query' : ''}
          value={query}
          onChange={(event) => { setIsAutoQuery(false); setQuery(event.target.value); }}
          onKeyDown={(event) => { if (event.key === 'Enter') runSearch(query.trim().replace(/\s+/g, ' ')); }}
          placeholder="Enter Product or Batch..."
        />
        <label className="stock-only-filter">
          <input type="checkbox" checked={onlyStock} onChange={(event) => setOnlyStock(event.target.checked)} />
          Stock only
        </label>
        {tenants.length > 1 && (
          <label className="tenant-filter">
            Tenant
            <select value={settings?.tenantId || ''} onChange={(event) => onTenantChange?.(event.target.value)}>
              {tenants.map((tenant) => (
                <option key={tenant.tenant_id} value={tenant.tenant_id}>
                  {tenant.tenant_name || tenant.tenant_code}
                </option>
              ))}
            </select>
          </label>
        )}
        <div className={`status-line ${status.state}`}>{status.message}</div>
        <div className="current-store-badge">
          <span>This device: {session?.user?.roles?.[0]?.store_name || settings?.storeName || 'Not registered'}</span>
          <button type="button" className="link-button" onClick={onOpenSettings}>Store order settings</button>
        </div>
      </div>

      <div className="top-summary-row">
        {warehouseStore && (
          <div className="store-row-workspace no-side-search warehouse-only top-summary-nmw">
            <section className="store-row-grid">
              <StoreDataRow
                key={warehouseStore.store_id || warehouseStore.store_code}
                store={warehouseStore}
                colorIndex={stores.indexOf(warehouseStore)}
                hasSearched={hasSearched}
                searchProducts={searchProductsByStore.get(warehouseStore.store_id) || []}
                detail={storeDetails[warehouseStore.store_id]}
                onProductSelect={(product) => handleProductSelect(warehouseStore.store_id, product)}
                onSaleSelect={(store, row) => setBillDetail({ store, sale: row })}
                onPurchaseSelect={canViewPurchase ? (row) => setPurchaseDetail({ store: warehouseStore, row }) : undefined}
                hideSupplierColumn={hideSupplierColumn}
                visibility={visibility}
                restrictWarehouse
                selected={selectedStoreId === warehouseStore.store_id}
                onSelect={() => setSelectedStoreId(warehouseStore.store_id)}
              />
            </section>
          </div>
        )}

        <NonMovingHighlightCard
          nonMovingProducts={filteredNonMoving}
          nonMovingLoading={nonMovingLoading}
          nonMovingIndex={nonMovingIndex}
          onPrev={() => nonMovingStep(-1)}
          onNext={() => nonMovingStep(1)}
          onSearch={(productName) => {
            if (!productName) return;
            setIsAutoQuery(false);
            setQuery(productName);
          }}
          allStores={allStores}
          storeFilter={nonMovingStoreFilter}
          onStoreFilterChange={setNonMovingStoreFilter}
        />
      </div>

      <div className="store-row-workspace no-side-search">
        <section className="store-row-grid">
          <StoreColumnHeaders hideSupplierColumn={hideSupplierColumn} sticky />
          {otherStores.map((store, index) => (
            <StoreDataRow
              key={store.store_id || store.store_code}
              store={store}
              colorIndex={stores.indexOf(store)}
              hasSearched={hasSearched}
              searchProducts={searchProductsByStore.get(store.store_id) || []}
              detail={storeDetails[store.store_id]}
              onProductSelect={(product) => handleProductSelect(store.store_id, product)}
              onSaleSelect={(s, row) => setBillDetail({ store: s, sale: row })}
              onPurchaseSelect={canViewPurchase ? (row) => setPurchaseDetail({ store, row }) : undefined}
              hideSupplierColumn={hideSupplierColumn}
              visibility={visibility}
              restrictWarehouse={false}
              selected={selectedStoreId === store.store_id}
              onSelect={() => setSelectedStoreId(store.store_id)}
            />
          ))}
        </section>
      </div>

      <ProductStatusLegend />

      {purchaseDetail && (
        <PurchaseDetailCard detail={purchaseDetail} onClose={() => setPurchaseDetail(null)} visibility={visibility} />
      )}
      {billDetail && (
        <BillDetailCard detail={billDetail} session={session} visibility={visibility} onClose={() => setBillDetail(null)} />
      )}
    </section>
  );
}

// A fixed 2-day starting default: day-before-yesterday through yesterday
// (still user-editable via the date pickers, unlike the earlier fixed-only
// version — the daily approval queue starts here but can be widened).
function nmwDefaultDateRange() {
  const fmt = (offsetDays) => {
    const d = new Date();
    d.setDate(d.getDate() - offsetDays);
    return d.toISOString().slice(0, 10);
  };
  return { dateFrom: fmt(2), dateTo: fmt(1) };
}

function nmwBillKey(bill) {
  return `${bill.bill_date}|${bill.bill_no}`;
}

function nmwCsvCell(value) {
  return `"${String(value ?? '').replace(/"/g, '""')}"`;
}

const NMW_EXPORT_COLUMNS = [
  'Inv No', 'Type', 'Inv Date', 'Customer Code', 'Inv Amount',
  'Product Code', 'Product', 'Batch', 'Expiry', 'Qty', 'Free', 'MRP', 'Rate', 'Dis%',
  'Packing', 'Sublocation', 'Amount'
];

function nmwDis2(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(2) : '0.00';
}

function nmwExportRows(bill, lineItems) {
  const base = [
    bill.bill_no, bill.bill_type || (bill.is_transfer ? 'Transfer' : 'Sale'), bill.bill_date,
    bill.customer_code, bill.bill_amount
  ];
  if (!lineItems || lineItems.length === 0) return [[...base, '', '', '', '', '', '', '', '', '0.00', '', '', '']];
  return lineItems.map((row) => [
    ...base,
    row.product_code, row.product_name, row.batch_no, row.expiry_date,
    row.qty, row.free_qty, row.mrp, row.rate, nmwDis2(row.discount_percentage),
    row.packing || '', row.sublocation || '', row.amount
  ]);
}

// NMW Sales Report (Bill-wise): warehouse -> store despatch bills, master/
// detail layout. Left: compact bill list (checkbox = bulk-select for Approve
// selected; row click = view that bill's items on the right). Right: the
// active bill's header + line items; the first bill is auto-selected on load.
// Cancelled bills are shown in red — viewable, but excluded from export.
// A super admin (or other broad role) sees EVERY store, pending + approved,
// and can approve + export. A store user is locked server-side to their own
// store's approved bills only — enforced by the API, not by what this screen
// requests. Whether THIS login is broad-access is read from the API response
// (can_approve / scope), not detected client-side — role name shapes differ
// across deployments, so the server is the only reliable source of truth.
function NmwSalesReport({ session, settings }) {
  const tenantId = settings?.tenantId || session?.user?.tenant_id || '';

  const [tenants, setTenants] = useState([]);
  const [stores, setStores] = useState([]);
  const [storeFilter, setStoreFilter] = useState('');
  const [range, setRange] = useState(nmwDefaultDateRange);

  const [bills, setBills] = useState([]);
  const [status, setStatus] = useState({ state: 'loading', message: 'Loading bills...' });
  const [activeKey, setActiveKey] = useState(null);
  const [items, setItems] = useState({});
  const [statusFilter, setStatusFilter] = useState('all');
  const [selected, setSelected] = useState(new Set());
  const [canApprove, setCanApprove] = useState(false);
  const [isBroad, setIsBroad] = useState(false);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    api.listTenants(session).then((rows) => setTenants(asArray(rows))).catch(() => {});
  }, [session]);

  useEffect(() => {
    api.listStores(session).then((rows) => setStores(asArray(rows))).catch(() => {});
  }, [session]);

  function loadItems(bill) {
    const key = nmwBillKey(bill);
    setActiveKey(key);
    if (!items[key] && bill.bill_no) {
      api.getNmwSalesBillItems(bill.bill_no, bill.bill_date, session, { tenantId })
        .then((result) => setItems((prev) => ({ ...prev, [key]: asArray(result?.items) })))
        .catch(() => setItems((prev) => ({ ...prev, [key]: [] })));
    }
  }

  function reload() {
    if (!tenantId) {
      setStatus({ state: 'idle', message: 'Waiting for device tenant/store configuration...' });
      return;
    }
    setStatus({ state: 'loading', message: 'Loading bills...' });
    setSelected(new Set());
    api.getNmwSalesBills(session, { status: statusFilter, tenantId, storeId: storeFilter, dateFrom: range.dateFrom, dateTo: range.dateTo })
      .then((result) => {
        const rows = asArray(result?.bills);
        setBills(rows);
        setCanApprove(Boolean(result?.can_approve));
        setIsBroad(result?.scope === 'all');
        setStatus({ state: 'ok', message: rows.length ? `${rows.length} bill(s).` : 'No bills for this filter.' });
        if (rows.length) loadItems(rows[0]);
        else setActiveKey(null);
      })
      .catch((error) => setStatus({ state: 'error', message: error.message }));
  }

  useEffect(() => { reload(); }, [session, tenantId, statusFilter]);

  function toggleSelect(bill) {
    const key = nmwBillKey(bill);
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  // Cancelled bills stay viewable but are never bulk-selectable/exportable.
  const pending = bills.filter((b) => b.status !== 'approved' && !b.is_cancelled);
  const allPendingSelected = pending.length > 0 && pending.every((b) => selected.has(nmwBillKey(b)));

  function toggleSelectAll() {
    setSelected(allPendingSelected ? new Set() : new Set(pending.map(nmwBillKey)));
  }

  function approveOne(bill) {
    api.approveNmwBills(tenantId, [{ bill_date: bill.bill_date, bill_no: bill.bill_no }], session)
      .then(() => reload())
      .catch((error) => setStatus({ state: 'error', message: error.message }));
  }

  function approveSelected() {
    const toApprove = pending
      .filter((b) => selected.has(nmwBillKey(b)))
      .map((b) => ({ bill_date: b.bill_date, bill_no: b.bill_no }));
    if (!toApprove.length) return;
    api.approveNmwBills(tenantId, toApprove, session)
      .then((result) => setStatus({ state: 'ok', message: `Approved ${result.approved} bill(s).` }))
      .then(reload)
      .catch((error) => setStatus({ state: 'error', message: error.message }));
  }

  // Export is scoped to the single bill currently open in the detail pane
  // (not the whole visible list) — the buttons live in that pane's header.
  // Cancelled bills are view-only: never exportable.
  async function exportBillAs(bill, format) {
    if (!bill || bill.is_cancelled || exporting) return;
    setExporting(true);
    setStatus({ state: 'loading', message: `Preparing ${format.toUpperCase()} export...` });
    try {
      const key = nmwBillKey(bill);
      let lineItems = items[key];
      if (!lineItems) {
        const result = await api.getNmwSalesBillItems(bill.bill_no, bill.bill_date, session, { tenantId });
        lineItems = asArray(result?.items);
        setItems((prev) => ({ ...prev, [key]: lineItems }));
      }
      const rows = nmwExportRows(bill, lineItems);
      const filename = `nmw-bill-${bill.bill_no}-${bill.bill_date}`.replace(/[^\w-]/g, '_');
      if (format === 'csv') {
        const csv = [NMW_EXPORT_COLUMNS, ...rows].map((r) => r.map(nmwCsvCell).join(',')).join('\n');
        const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
        downloadBlob(blob, `${filename}.csv`);
      } else {
        // xlsx-js-style (not the plain SheetJS community build) is the
        // dependency here specifically because it keeps cell .s style objects
        // on write for both xlsx and legacy biff8 - the plain xlsx package
        // silently drops all styling on write.
        const XLSX = await import('xlsx-js-style');
        const aoa = [NMW_EXPORT_COLUMNS, ...rows];
        const ws = XLSX.utils.aoa_to_sheet(aoa);
        const font = { name: 'Times New Roman', sz: 10 };
        for (let r = 0; r < aoa.length; r += 1) {
          for (let c = 0; c < NMW_EXPORT_COLUMNS.length; c += 1) {
            const ref = XLSX.utils.encode_cell({ r, c });
            const cell = ws[ref];
            if (!cell) continue;
            cell.s = { font: r === 0 ? { ...font, bold: true } : font };
          }
        }
        const wb = XLSX.utils.book_new();
        XLSX.utils.book_append_sheet(wb, ws, 'NMW Sales');
        const bookType = format === 'xls' ? 'biff8' : 'xlsx';
        const ext = format === 'xls' ? 'xls' : 'xlsx';
        const buffer = XLSX.write(wb, { bookType, type: 'array', cellStyles: true });
        downloadBlob(new Blob([buffer], { type: 'application/octet-stream' }), `${filename}.${ext}`);
      }
      setStatus({ state: 'ok', message: `Exported bill ${bill.bill_no} (${format.toUpperCase()}).` });
    } catch (error) {
      setStatus({ state: 'error', message: error.message });
    } finally {
      setExporting(false);
    }
  }

  function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
  }

  const activeBill = bills.find((b) => nmwBillKey(b) === activeKey) || null;
  const activeItems = activeKey ? items[activeKey] : undefined;

  return (
    <section className="screen-panel nmw-report-screen">
      <div className="nmw-toolbar">
        <strong className="nmw-toolbar-title">NMW Sales Report</strong>

        <label className="nmw-toolbar-field">
          Tenant
          <select value={tenantId} disabled>
            {tenants.length === 0 && <option value={tenantId}>{tenantId ? 'Current tenant' : 'Loading...'}</option>}
            {tenants.map((t) => (
              <option key={t.tenant_id} value={t.tenant_id}>{t.tenant_name}</option>
            ))}
          </select>
        </label>

        {isBroad && (
          <label className="nmw-toolbar-field">
            Store
            <select value={storeFilter} onChange={(event) => setStoreFilter(event.target.value)}>
              <option value="">All stores</option>
              {stores.map((s) => (
                <option key={s.store_id} value={s.store_id}>{s.store_code} — {s.store_name}</option>
              ))}
            </select>
          </label>
        )}

        <label className="nmw-toolbar-field">
          From
          <input type="date" value={range.dateFrom} onChange={(event) => setRange((prev) => ({ ...prev, dateFrom: event.target.value }))} />
        </label>
        <label className="nmw-toolbar-field">
          To
          <input type="date" value={range.dateTo} onChange={(event) => setRange((prev) => ({ ...prev, dateTo: event.target.value }))} />
        </label>
        <label className="nmw-toolbar-field">
          Status
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <option value="all">All</option>
            <option value="pending">Pending</option>
            <option value="approved">Approved</option>
          </select>
        </label>

        <button className="secondary-button" onClick={reload}>Load</button>

        {canApprove && (
          <button className="primary-button" disabled={selected.size === 0} onClick={approveSelected}>
            Approve selected ({selected.size})
          </button>
        )}
      </div>

      <div className={`status-line ${status.state}`}>{status.message}</div>

      {bills.length > 0 && (
        <div className="nmw-split">
          <div className="table-wrap nmw-bill-list-pane">
            <table className="nmw-compact-table">
              <thead>
                <tr>
                  {canApprove && (
                    <th>
                      <input type="checkbox" checked={allPendingSelected} disabled={pending.length === 0} onChange={toggleSelectAll} />
                    </th>
                  )}
                  <th>Bill No</th>
                  <th>Type</th>
                  <th>Date</th>
                  {isBroad && <th>Store</th>}
                  <th>Amount</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {bills.map((bill) => {
                  const key = nmwBillKey(bill);
                  const isApproved = bill.status === 'approved';
                  return (
                    <tr
                      key={key}
                      className={`${activeKey === key ? 'nmw-row-active' : ''} ${bill.is_cancelled ? 'nmw-row-cancelled' : ''}`}
                      onClick={() => loadItems(bill)}
                    >
                      {canApprove && (
                        <td onClick={(event) => event.stopPropagation()}>
                          {!isApproved && !bill.is_cancelled && (
                            <input type="checkbox" checked={selected.has(key)} onChange={() => toggleSelect(bill)} />
                          )}
                        </td>
                      )}
                      <td>{bill.bill_no}</td>
                      <td>{bill.bill_type || (bill.is_transfer ? 'Transfer' : 'Sale')}</td>
                      <td>{formatDate(bill.bill_date)}</td>
                      {isBroad && <td>{bill.dest_store_code}</td>}
                      <td>{formatMoney(bill.bill_amount)}</td>
                      <td>{bill.is_cancelled ? 'Cancelled' : isApproved ? 'Approved' : 'Pending'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="table-wrap nmw-bill-detail-pane">
            {!activeBill ? (
              <div className="empty-state">Select a bill to view its items.</div>
            ) : (
              <>
                <div className="nmw-bill-detail-head">
                  <div className={activeBill.is_cancelled ? 'nmw-row-cancelled' : ''}>
                    <strong>{activeBill.bill_no}</strong> · {activeBill.bill_type || (activeBill.is_transfer ? 'Transfer' : 'Sale')}
                    <span className="nmw-bill-detail-sub">
                      {formatDate(activeBill.bill_date)} · {activeBill.dest_store_code} — {activeBill.dest_store_name} · {formatMoney(activeBill.bill_amount)}
                      {' · '}{activeBill.is_cancelled ? 'Cancelled' : activeBill.status === 'approved' ? 'Approved' : 'Pending'}
                      {activeBill.approved_by ? ` by ${activeBill.approved_by}` : ''}
                    </span>
                  </div>
                  <div className="nmw-bill-detail-actions">
                    {!activeBill.is_cancelled && (
                      <div className="nmw-export-group">
                        <button className="nmw-icon-button" disabled={exporting} onClick={() => exportBillAs(activeBill, 'csv')} title="Export this bill as CSV">
                          ⬇ CSV
                        </button>
                        <button className="nmw-icon-button" disabled={exporting} onClick={() => exportBillAs(activeBill, 'xlsx')} title="Export this bill as XLSX">
                          ⬇ XLSX
                        </button>
                        <button className="nmw-icon-button" disabled={exporting} onClick={() => exportBillAs(activeBill, 'xls')} title="Export this bill as Excel 97-2003">
                          ⬇ XLS
                        </button>
                      </div>
                    )}
                    {canApprove && !activeBill.is_cancelled && activeBill.status !== 'approved' && (
                      <button className="primary-button" onClick={() => approveOne(activeBill)}>Approve this bill</button>
                    )}
                  </div>
                </div>

                {!activeItems ? (
                  <div className="empty-state">Loading items...</div>
                ) : activeItems.length === 0 ? (
                  <div className="empty-state">No line items.</div>
                ) : (
                  <table className="nmw-compact-table">
                    <thead>
                      <tr>
                        <th>Product Code</th><th>Product</th><th>Batch</th><th>Expiry</th>
                        <th>Qty</th><th>Free</th><th>MRP</th><th>Rate</th><th>Dis%</th><th>Amount</th>
                      </tr>
                    </thead>
                    <tbody>
                      {activeItems.map((row, index) => (
                        <tr key={`${row.product_code}-${row.batch_no}-${index}`}>
                          <td>{row.product_code}</td>
                          <td>{row.product_name}</td>
                          <td>{row.batch_no}</td>
                          <td>{formatDate(row.expiry_date)}</td>
                          <td>{formatQty(row.qty)}</td>
                          <td>{formatQty(row.free_qty)}</td>
                          <td>{formatMoney(row.mrp)}</td>
                          <td>{formatMoney(row.rate)}</td>
                          <td>{row.discount_percentage}</td>
                          <td>{formatMoney(row.amount)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

const STORE_COLORS = ['#2563eb', '#15803d', '#b45309', '#7c3aed', '#be123c', '#0d9488'];

const STOCK_COLS = 'minmax(0, 1.35fr) 40px 44px';
// Legacy 4-col batch layout, still used by the Supplier Stock Analysis
// screen's own Batch panel (different data source - no purchase/sales age).
const BATCH_COLS = '68px 46px 58px 78px';
// Stock Availability's enriched Batch grid (§2/§4/§5/§8): Exp (date +
// days-remaining subtitle) | Stock | MRP | Batch No | Purchase Age |
// Sales Age | Status | Priority icon
const BATCH_DETAIL_COLS = '78px 40px 52px 62px 62px 62px 84px 22px';
// Supplier gets the freed-up width (Qty/Free/GRN Date/GRN No trimmed) so
// long supplier names stop truncating.
const PURCHASE_COLS = '24px 22px 52px 56px 64px 52px minmax(132px, 1fr)';
const PURCHASE_COLS_NO_SUPPLIER = '32px 32px 64px 58px 54px 54px 58px';
// Merged Billing History summary grid: Qty | Dis% | Date | Bill No | Product | MRP | Amount | ▶
const BILLING_COLS = '34px 44px 58px 64px 1fr 56px 64px 16px';
// Legacy per-store "Sales" tab in StoreDetailBody (Bill No/Date get more room, Qty/Dis%/MRP get less).
const SALES_COLS = '26px 68px 104px 24px 1fr 38px';

function StoreColumnHeaders({ hideSupplierColumn = false, restrictWarehouse = false, sticky = false, showBillingColumn = true }) {
  const purchaseCols = hideSupplierColumn ? PURCHASE_COLS_NO_SUPPLIER : PURCHASE_COLS;
  const purchaseHeaders = hideSupplierColumn
    ? ['Qty', 'Free', 'GRN Date', 'GRN No', 'MRP', 'PTR', 'Cost']
    : ['Qty', 'Free', 'All Dis', 'Prod Dis%', 'GRN Date', 'GRN No', 'Supplier'];

  if (restrictWarehouse) {
    return (
      <div className={`store-column-headers ${sticky ? 'sticky' : ''}`}>
        <span className="store-header-cell" />
        <div className="header-cell warehouse-only-header-cell">
          <div className="header-cell-title">📦 Product</div>
          <GridRow cols={STOCK_COLS} cells={['Product', 'Unit', 'Stock']} tag="span" />
        </div>
      </div>
    );
  }

  return (
    <div className={`store-column-headers ${sticky ? 'sticky' : ''} ${showBillingColumn ? '' : 'no-bill-column'}`}>
      <span className="store-header-cell" />
      <div className="header-cell">
        <div className="header-cell-title">📦 Product</div>
        <GridRow cols={STOCK_COLS} cells={['Product', 'Unit', 'Stock']} tag="span" />
      </div>
      <div className="header-cell">
        <div className="header-cell-title">📈 Sales Trend</div>
      </div>
      <div className="header-cell">
        <div className="header-cell-title">🗓 Batches</div>
        <GridRow cols={BATCH_DETAIL_COLS} cells={['Exp', 'Stk', 'MRP', 'Batch No', 'Pur. Age', 'Sale Age', 'Status', '']} tag="span" />
      </div>
      <div className="header-cell">
        <div className="header-cell-title">🛒 Purchase History</div>
        <GridRow cols={purchaseCols} cells={purchaseHeaders} tag="span" />
      </div>
      {showBillingColumn && (
        <div className="header-cell">
          <div className="header-cell-title">🧾 Billing History</div>
          <GridRow cols={BILLING_COLS} cells={['Qty', 'Dis%', 'Date', 'Bill No', 'Product', 'MRP', 'Amount', '']} tag="span" />
        </div>
      )}
    </div>
  );
}

function GridRow({ cols, cells, tag: Tag = 'div', className = '', onClick }) {
  return (
    <div className={`grid-row ${className}`} style={{ gridTemplateColumns: cols }} onClick={onClick}>
      {cells.map((cell, index) => <Tag key={index}>{cell}</Tag>)}
    </div>
  );
}

function StoreDataRow({ store, colorIndex, hasSearched, searchProducts, detail, onProductSelect, onSaleSelect, onPurchaseSelect, hideSupplierColumn, restrictWarehouse, selected, onSelect, showBillingColumn = true, visibility = 'SUMMARY', rowRef }) {
  const batches = detail?.batches || [];
  const purchases = detail?.purchases || [];
  const sales = detail?.sales || [];
  const movement = detail?.movement || [];
  const storeColor = STORE_COLORS[colorIndex % STORE_COLORS.length];
  const currentProduct = detail?.product?.product_name;
  const pending = hasSearched && searchProducts.length > 0 && detail === undefined;
  const batchSummary = summarizeProductBatches(batches);

  const statusText = currentProduct
    ? `${restrictWarehouse ? '' : 'Showing: '}${currentProduct}`
    : pending ? 'Loading...' : hasSearched ? 'No product selected' : 'Waiting for search...';

  // §6: one compact procurement-decision line under the product name -
  // "what should I avoid / which batches expire soon / dead stock" at a
  // glance, without opening the Batch grid.
  const batchInfoLine = batchSummary && (
    [
      batchSummary.expiredCount ? `Expired: ${batchSummary.expiredCount}` : null,
      batchSummary.nearExpiryCount ? `Near Expiry: ${batchSummary.nearExpiryCount}` : null,
      batchSummary.nonMoving ? 'Non Moving: Yes' : null
    ].filter(Boolean).join(' · ') || 'Healthy'
  );

  return (
    <article
      ref={rowRef}
      className={`store-data-row ${selected ? 'selected' : ''} ${pending ? 'pending' : ''}`}
      style={{ '--store-color': storeColor }}
    >
      {restrictWarehouse && (
        <StoreColumnHeaders
          hideSupplierColumn={hideSupplierColumn}
          restrictWarehouse={restrictWarehouse}
          showBillingColumn={showBillingColumn}
        />
      )}

      <div className={`store-row-grid-body ${showBillingColumn ? '' : 'no-bill-column'}`} onClick={onSelect}>
        <div className="store-row-label" title={store.store_name || 'Loading store...'}>
          {store.store_code ? (
            store.store_code.split('').map((char, index) => <strong key={index}>{char}</strong>)
          ) : (
            <span className="store-row-label-spinner" aria-hidden="true" />
          )}
        </div>

        <section className={`row-cell stock-cell ${restrictWarehouse ? 'stock-cell-full' : ''}`}>
          <div className="stock-cell-status">
            {statusText}
            {!restrictWarehouse && batchInfoLine && (
              <span className={`stock-cell-batch-info stock-cell-batch-info--${batchSummary.status}`}> · {batchInfoLine}</span>
            )}
          </div>
          <StoreProductGrid
            products={searchProducts}
            hasSearched={hasSearched}
            selectedProductCode={detail?.product?.product_code}
            onProductSelect={onProductSelect}
            activeSummary={batchSummary}
          />
        </section>

        {restrictWarehouse ? null : (
          <>
            <section className="row-cell trend-cell">
              {pending ? <SkeletonBlock lines={1} /> : <MonthlyMovementChart rows={movement} purchases={purchases} sales={sales} />}
            </section>

            <BatchTable rows={batches} pending={pending} />

            <RowDataCell
              className={`purchase-table ${hideSupplierColumn ? 'summary-cols' : ''} ${onPurchaseSelect ? 'clickable' : ''}`}
              cols={hideSupplierColumn ? PURCHASE_COLS_NO_SUPPLIER : PURCHASE_COLS}
              emptyMessage="No purchase details."
              pending={pending}
              rows={purchases.slice(0, 20).map((row) => (hideSupplierColumn
                ? [
                  formatQty(row.qty),
                  formatQty(row.free ?? 0),
                  formatDate(row.date),
                  row.grn_no || '-',
                  formatMoney(row.mrp),
                  formatMoney(row.ptr ?? row.purchase_price),
                  formatMoney(row.cost)
                ]
                : [
                  formatQty(row.qty),
                  formatQty(row.free ?? 0),
                  formatMoney(row.overall_discount ?? row.discount_amount),
                  formatMoney(row.discount ?? row.dis),
                  formatDate(row.date),
                  row.grn_no || '-',
                  visibility === 'FULL' ? (row.supplier || '-') : abbreviateSupplierName(row.supplier)
                ]))}
              onRowClick={onPurchaseSelect ? (index) => onPurchaseSelect(purchases[index]) : undefined}
            />

            {showBillingColumn && (
              <section className="row-cell row-data-cell bill-table">
                {pending ? (
                  <SkeletonBlock lines={4} />
                ) : sales.length ? (
                  <div className="row-table-wrap">
                    {sales.slice(0, 20).map((row, index) => {
                      const qty = Number(row.qty) || 0;
                      const mrp = Number(row.mrp) || 0;
                      const discount = Number(row.discount) || 0;
                      const amount = qty * mrp * (1 - discount / 100);
                      const productLabel = row.extra_item_count
                        ? `${currentProduct || '-'} + ${row.extra_item_count} more`
                        : (currentProduct || '-');
                      return (
                        <GridRow
                          key={index}
                          cols={BILLING_COLS}
                          tag="span"
                          className="num-row"
                          cells={[
                            formatQty(qty),
                            formatMoney(discount),
                            formatDate(row.date),
                            row.bill_no || '-',
                            <span className="product-cell-main" title={productLabel}>{productLabel}</span>,
                            formatMoney(mrp),
                            formatMoney(amount),
                            '▶'
                          ]}
                          onClick={onSaleSelect ? () => onSaleSelect(store, row) : undefined}
                        />
                      );
                    })}
                  </div>
                ) : (
                  <div className="row-empty-state">No billing details.</div>
                )}
              </section>
            )}
          </>
        )}
      </div>
    </article>
  );
}

const PURCHASE_DETAIL_FIELDS = [
  ['supplier', 'Supplier'],
  ['grn_no', 'GRN No'],
  ['date', 'GRN Date'],
  ['qty', 'Qty'],
  ['free', 'Free'],
  ['mrp', 'MRP'],
  ['ptr', 'PTR'],
  ['cost', 'Cost'],
  ['dis_pct', 'Dis%']
];

const PURCHASE_MONEY_FIELDS = new Set(['mrp', 'ptr', 'cost']);
// Fields only a FULL-visibility user (super admin / purchase role) may see.
const PURCHASE_FULL_ONLY_FIELDS = new Set(['supplier', 'dis_pct']);

function PurchaseDetailCard({ detail, onClose, visibility = 'SUMMARY' }) {
  const { store, row } = detail;
  const fields = PURCHASE_DETAIL_FIELDS.filter(([key]) => visibility === 'FULL' || !PURCHASE_FULL_ONLY_FIELDS.has(key));
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="purchase-detail-card" onClick={(event) => event.stopPropagation()}>
        <div className="purchase-detail-header">
          <strong>Purchase Details · {store.store_name || store.store_code}</strong>
          <button type="button" className="ghost-button" onClick={onClose}>Close</button>
        </div>
        <div className="purchase-detail-grid">
          {fields.filter(([key]) => row[key] !== undefined && row[key] !== null && row[key] !== '').map(([key, label]) => (
            <div className="purchase-detail-item" key={key}>
              <span>{label}</span>
              <strong className={PURCHASE_MONEY_FIELDS.has(key) ? 'num-value' : ''}>
                {key === 'date' ? formatDate(row[key])
                  : PURCHASE_MONEY_FIELDS.has(key) ? formatMoney(row[key])
                  : row[key]}
              </strong>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function BillDetailCard({ detail, session, visibility = 'SUMMARY', onClose }) {
  const { store, sale } = detail;
  const [items, setItems] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setItems(null);
    setFailed(false);
    api.getBillItems(store.store_id, sale.bill_no, sale.date, session)
      .then((result) => { if (!cancelled) setItems(asArray(result)); })
      .catch(() => { if (!cancelled) setFailed(true); });
    return () => { cancelled = true; };
  }, [store.store_id, sale.bill_no, sale.date]);

  const rows = items || [];
  const total = rows.reduce((sum, row) => sum + (Number(row.amount) || 0), 0);
  const salesman = rows[0]?.salesman || sale.salesman;
  const customer = sale.customer || rows[0]?.customer;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="purchase-detail-card bill-detail-card" onClick={(event) => event.stopPropagation()}>
        <div className="purchase-detail-header">
          <strong>Bill {sale.bill_no} · {store.store_name || store.store_code}</strong>
          <button type="button" className="ghost-button" onClick={onClose}>Close</button>
        </div>
        <div className="purchase-detail-grid">
          <div className="purchase-detail-item"><span>Bill Date</span><strong>{formatDate(sale.date)}</strong></div>
          {visibility !== 'NONE' && customer && (
            <div className="purchase-detail-item"><span>Customer</span><strong>{visibility === 'FULL' ? customer : abbreviateSupplierName(customer, 14)}</strong></div>
          )}
          {visibility === 'FULL' && salesman && (
            <div className="purchase-detail-item"><span>Salesman</span><strong>{salesman}</strong></div>
          )}
          <div className="purchase-detail-item"><span>Total Amount</span><strong className="num-value">{items ? formatMoney(total) : '-'}</strong></div>
        </div>

        <div className="bill-detail-products">
          {items === null && !failed && <SkeletonBlock lines={4} />}
          {failed && <div className="row-empty-state">Unable to load bill items.</div>}
          {items !== null && !failed && (
            rows.length ? (
              <table className="bill-detail-table">
                <thead>
                  <tr>
                    <th>Product</th>
                    <th className="num-col">Qty</th>
                    <th className="num-col">MRP</th>
                    {visibility === 'FULL' && <th className="num-col">PTR</th>}
                    <th className="num-col">Dis%</th>
                    <th className="num-col">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, index) => (
                    <tr key={index}>
                      <td>{row.product_name || '-'}</td>
                      <td className="num-col">{formatQty(row.qty)}</td>
                      <td className="num-col">{formatMoney(row.mrp)}</td>
                      {visibility === 'FULL' && <td className="num-col">{formatMoney(row.ptr)}</td>}
                      <td className="num-col">{formatMoney(row.discount_pct)}</td>
                      <td className="num-col">{formatMoney(row.amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="row-empty-state">No bill line items found.</div>
            )
          )}
        </div>
      </div>
    </div>
  );
}

function RowDataCell({ className, cols, rows, emptyMessage, highlightIndex, pending, onRowClick }) {
  return (
    <section className={`row-cell row-data-cell ${className}`}>
      {pending ? (
        <SkeletonBlock lines={4} />
      ) : rows.length ? (
        <div className="row-table-wrap">
          {rows.map((row, index) => (
            <GridRow
              key={index}
              cols={cols}
              cells={row}
              tag="span"
              className={index === highlightIndex ? 'active-row' : ''}
              onClick={onRowClick ? () => onRowClick(index) : undefined}
            />
          ))}
        </div>
      ) : (
        <div className="row-empty-state">{emptyMessage}</div>
      )}
    </section>
  );
}

// §2/§3/§8: the Batch grid is the primary procurement-decision panel -
// Status/Priority columns, expiry + days-remaining together, sorted worst
// (Expired) first so the buyer never has to scan for risk.
function BatchTable({ rows, pending }) {
  if (pending) {
    return (
      <section className="row-cell row-data-cell batch-table">
        <SkeletonBlock lines={4} />
      </section>
    );
  }
  if (!rows.length) {
    return (
      <section className="row-cell row-data-cell batch-table">
        <div className="row-empty-state">No batch details.</div>
      </section>
    );
  }
  // §2: every batch is shown, including zero-stock ones - only the render
  // order changes (usable stock first), nothing is hidden or dropped.
  const sorted = sortedBatches(rows);
  return (
    <section className="row-cell row-data-cell batch-table">
      <div className="row-table-wrap">
        {sorted.map((row, index) => {
          const status = batchStatus(row);
          const meta = BATCH_STATUS_META[status];
          const expiryDate = row.expiry_date || row.expirydate;
          const batchNo = row.batch_no || row.batchcode;
          const purchaseAge = ageInfo(row.last_purchase_date || row.grndate);
          const salesAge = ageInfo(row.last_sale_date || row.lastsaledate);
          return (
            <div key={index} className={`grid-row batch-row batch-row--${status}`} style={{ gridTemplateColumns: BATCH_DETAIL_COLS }}>
              <span className="batch-cell-expiry">
                {formatDate(expiryDate)}
              </span>
              <span>{formatQty(row.stock)}</span>
              <span>{formatMoney(row.mrp)}</span>
              <span>{batchNo || '-'}</span>
              <span className="batch-age batch-age--purchase">{purchaseAge.text}</span>
              <span className="batch-age batch-age--sales">{salesAge.text}</span>
              <span className="batch-cell-status">{meta.label}</span>
              <span className="batch-cell-priority" title={meta.label}>{meta.icon}</span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function SkeletonBlock({ lines = 3 }) {
  return (
    <div className="skeleton-block">
      {Array.from({ length: lines }, (_, index) => <span key={index} className="skeleton-line" />)}
    </div>
  );
}

// Product-level rollup from its currently-loaded batches (§5/§6). Only the
// selected/active product has batch data fetched, so this can only be shown
// for that one row - the other listed matches don't have batch data without
// an extra fetch per row, which would multiply API calls per store row list.
//
// Product status must reflect ACTIVE STOCK ONLY - a batch sitting at
// Stock = 0 can be expired/near-expiry/whatever it likes without it ever
// being able to affect what the buyer sees on this product, since there's
// nothing left of it to sell, expire in the warehouse, or restock around.
function summarizeProductBatches(batches) {
  const activeBatches = (batches || []).filter((row) => (Number(row.stock) || 0) > 0);
  if (!activeBatches.length) return null;
  const statuses = activeBatches.map(batchStatus);
  const allActiveNonMoving = statuses.every((status) => status === 'non-moving');
  const worst = statuses.reduce(
    (acc, status) => (BATCH_STATUS_META[status].order < BATCH_STATUS_META[acc].order ? status : acc),
    'healthy'
  );
  return {
    status: worst === 'non-moving' && !allActiveNonMoving ? 'healthy' : worst,
    expiredCount: statuses.filter((status) => status === 'expired').length,
    nearExpiryCount: statuses.filter((status) => status === 'near-expiry').length,
    nonMoving: allActiveNonMoving
  };
}

function StoreProductGrid({ products, hasSearched, selectedProductCode, onProductSelect, activeSummary }) {
  if (!products.length) {
    return <div className={hasSearched ? 'not-found-card' : 'waiting-card'}>{hasSearched ? 'No matching products.' : 'Waiting.'}</div>;
  }

  return (
    <div className="store-product-grid-wrap">
      {products.slice(0, 20).map((product, index) => {
        const isActive = product.product_code === selectedProductCode;
        const summary = isActive ? activeSummary : null;
        const matchBadge = product.matchBadge;
        return (
          <GridRow
            key={`${product.product_code || product.product_name}-${index}`}
            cols={STOCK_COLS}
            tag="span"
            className={isActive ? 'active-row' : ''}
            cells={[
              <span className="product-cell-main" title={product.product_name || '-'}>
                {summary && (
                  <span className="product-status-badge" title={BATCH_STATUS_META[summary.status].label}>
                    {BATCH_STATUS_META[summary.status].icon}
                  </span>
                )}
                <span className="product-name-with-badge">
                  <span>{product.product_name || '-'}</span>
                  {matchBadge && (
                    <span className={`match-badge match-badge--${matchBadge.className || 'similar'}`} title={matchBadge.title}>
                      {matchBadge.label}
                    </span>
                  )}
                </span>
              </span>,
              <span className="product-cell-unit">{product.sale_unit || product.unitdescription || '-'}</span>,
              <span className={`product-cell-stock ${(Number(product.stock) || 0) > 0 ? 'product-cell-stock--available' : 'product-cell-stock--zero'}`}>
                {product.stock ?? 0}
              </span>
            ]}
            onClick={() => onProductSelect(product)}
          />
        );
      })}
    </div>
  );
}

function ProductStatusLegend() {
  return (
    <div className="product-status-legend">
      {Object.values(BATCH_STATUS_META).map((meta) => (
        <span key={meta.label}>{meta.icon} {meta.label}</span>
      ))}
    </div>
  );
}

function shortStoreName(value) {
  return String(value || 'STORE').replace(/^Nathan\s+Medicals\s*/i, '').slice(0, 4).toUpperCase() || 'STORE';
}

function storeLabel(store) {
  if (store?.store_code) return store.store_code;
  const name = String(store?.store_name || '').replace(/^Nathan\s+Medicals\s*/i, '').trim();
  return name ? `NM${name.toUpperCase()}` : 'STORE';
}

function candidateMatchMeta(sourceName, targetName, score = 0) {
  const strictSource = normalizeForBadge(sourceName);
  const strictTarget = normalizeForBadge(targetName);
  if (strictSource && strictSource === strictTarget) {
    return { priority: 2, badge: { label: 'EXACT MATCH', className: 'exact' } };
  }

  const compactSource = normalizeForLooseExact(sourceName);
  const compactTarget = normalizeForLooseExact(targetName);
  if (compactSource && compactSource === compactTarget) {
    return {
      priority: 1,
      badge: {
        label: 'NORMALIZED EXACT',
        className: 'exact',
        title: 'Matched after compact normalization of units and dosage words'
      }
    };
  }

  return {
    priority: 0,
    badge: {
      label: `${Math.round(score || 0)}%`,
      className: 'similar',
      title: `Similar match ${Math.round(score || 0)}%`
    }
  };
}

function productTooltip(row) {
  const parts = [];
  if (row.mrp !== undefined && row.mrp !== null && row.mrp !== '') parts.push(`MRP: ${row.mrp}`);
  if (row.ptr !== undefined && row.ptr !== null && row.ptr !== '') parts.push(`PTR: ${row.ptr}`);
  if (row.discount !== undefined && row.discount !== null && row.discount !== '' && Number(row.discount) !== 0) parts.push(`Discount: ${row.discount}%`);
  if (row.packing) parts.push(`Packing: ${row.packing}`);
  if (row.scheme) parts.push(`Scheme/Offer: ${row.scheme}`);
  if (row.free !== undefined && row.free !== null && Number(row.free) !== 0) parts.push(`Free: ${row.free}`);
  return parts.length ? parts.join('  |  ') : 'No discount/offer details available.';
}

function procurementDraftStorageKey(tenantId, storeId, supplierCode) {
  return `nexora.desktop.procurementDrafts:${tenantId || 'tenant'}:${storeId || 'store'}:${supplierCode || 'supplier'}`;
}

function loadProcurementDrafts(tenantId, storeId, supplierCode) {
  try {
    const raw = localStorage.getItem(procurementDraftStorageKey(tenantId, storeId, supplierCode));
    const parsed = raw ? JSON.parse(raw) : null;
    return {
      qty: parsed?.qty && typeof parsed.qty === 'object' ? parsed.qty : {},
      remarks: parsed?.remarks && typeof parsed.remarks === 'object' ? parsed.remarks : {}
    };
  } catch {
    return { qty: {}, remarks: {} };
  }
}

function saveProcurementDrafts(tenantId, storeId, supplierCode, qty, remarks) {
  try {
    localStorage.setItem(procurementDraftStorageKey(tenantId, storeId, supplierCode), JSON.stringify({ qty, remarks }));
  } catch {
    // Best effort persistence only.
  }
}

function sanitizeOrderQty(value) {
  return String(value ?? '')
    .toUpperCase()
    .replace(/[^A-Z0-9+ ]/g, '')
    .replace(/\s+/g, ' ')
    .trimStart()
    .slice(0, 8);
}

function parseOrderQty(value) {
  const text = String(value ?? '').trim();
  if (!text) return 0;
  const firstNumber = text.match(/\d+/);
  if (!firstNumber) return 0;
  const qty = Number.parseInt(firstNumber[0], 10);
  return Number.isFinite(qty) && qty > 0 ? qty : 0;
}

function offerBadge(row) {
  const buy = Number(row.scheme || 0);
  const free = Number(row.free || 0);
  const discount = Number(row.discount || 0);
  if (buy > 0 && free > 0) return `${buy}+${free}`.slice(0, 8);
  if (discount > 0) return `${discount}%`.slice(0, 8);
  return '';
}

function offerTooltipLines(row) {
  const buy = Number(row.scheme || 0);
  const free = Number(row.free || 0);
  const discount = Number(row.discount || 0);
  const badge = offerBadge(row);
  if (!badge) return [];
  return [
    ['Offer Name', buy > 0 && free > 0 ? 'Buy + Free' : discount > 0 ? 'Discount' : 'Offer'],
    ['Buy Qty', buy > 0 ? buy : '—'],
    ['Free Qty', free > 0 ? free : '—'],
    ['Discount', discount > 0 ? `${discount}%` : '—'],
    ['Valid Until', row.transaction_date ? formatDate(row.transaction_date) : '—'],
    ['Supplier Remarks', row.scheme || '—']
  ];
}

function downloadTextFile(filename, text, mimeType = 'text/plain;charset=utf-8') {
  const blob = new Blob([text], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function csvCell(value) {
  const text = String(value ?? '');
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function orderStores(rows, loginStoreId, storeOrder = []) {
  const rank = new Map(storeOrder.map((storeId, index) => [storeId, index]));
  return [...rows].sort((a, b) => {
    const warehouseA = isWarehouseStore(a) ? 0 : 1;
    const warehouseB = isWarehouseStore(b) ? 0 : 1;
    if (warehouseA !== warehouseB) return warehouseA - warehouseB;
    if (a.store_id === loginStoreId) return -1;
    if (b.store_id === loginStoreId) return 1;
    const rankA = rank.has(a.store_id) ? rank.get(a.store_id) : Infinity;
    const rankB = rank.has(b.store_id) ? rank.get(b.store_id) : Infinity;
    if (rankA !== rankB) return rankA - rankB;
    return String(a.store_name || a.store_code || '').localeCompare(String(b.store_name || b.store_code || ''));
  });
}

function monthKey(value) {
  if (!value) return '';
  const raw = String(value).trim();
  const isoMatch = raw.match(/^(\d{4})-(\d{2})/);
  if (isoMatch) return `${isoMatch[1]}-${isoMatch[2]}`;
  const slashMatch = raw.match(/^(\d{1,2})\/(\d{1,2})\/(\d{2,4})$/);
  if (slashMatch) {
    const year = slashMatch[3].length === 2 ? `20${slashMatch[3]}` : slashMatch[3];
    return `${year}-${slashMatch[2].padStart(2, '0')}`;
  }
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) return '';
  return `${parsed.getFullYear()}-${String(parsed.getMonth() + 1).padStart(2, '0')}`;
}

function buildChartRows(rows, purchases = [], sales = []) {
  const movementRows = Array.isArray(rows) ? rows : [];
  const orderedKeys = [];
  const byMonth = new Map();
  const ensureMonth = (key) => {
    if (!key) return null;
    if (!byMonth.has(key)) {
      orderedKeys.push(key);
      byMonth.set(key, { period: key, pur: 0, tin: 0, sal: 0, tout: 0, stk: 0 });
    }
    return byMonth.get(key);
  };

  movementRows.forEach((row) => {
    const key = monthKey(row.period || row.month);
    if (!key) return;
    ensureMonth(key);
    byMonth.set(key, {
      period: key,
      pur: Number(row.pur || 0),
      tin: Number(row.tin || 0),
      sal: Number(row.sal || 0),
      tout: Number(row.tout || 0),
      stk: Number(row.stk || 0)
    });
  });

  if (!orderedKeys.length) {
    const base = new Date();
    base.setDate(1);
    for (let offset = 3; offset >= 0; offset -= 1) {
      const point = new Date(base.getFullYear(), base.getMonth() - offset, 1);
      const key = `${point.getFullYear()}-${String(point.getMonth() + 1).padStart(2, '0')}`;
      orderedKeys.push(key);
      byMonth.set(key, { period: key, pur: 0, tin: 0, sal: 0, tout: 0, stk: 0 });
    }
  }

  purchases.forEach((row) => {
    const key = monthKey(row.grndate || row.date);
    const target = ensureMonth(key);
    if (!target) return;
    if (!target.pur && !target.tin) {
      target.pur += Number(row.qty || 0) + Number(row.free || 0);
    }
  });

  sales.forEach((row) => {
    const key = monthKey(row.bill_date || row.date);
    const target = ensureMonth(key);
    if (!target) return;
    if (!target.sal && !target.tout) {
      target.sal += Number(row.qty || 0);
    }
  });

  orderedKeys.sort((a, b) => a.localeCompare(b));
  return orderedKeys.slice(-4).map((key) => byMonth.get(key));
}

function MonthlyMovementChart({ rows, purchases = [], sales = [] }) {
  const months = buildChartRows(rows, purchases, sales);
  if (!months.length) return <div className="empty-state">No chart data yet.</div>;

  const maxValue = Math.max(1, ...months.flatMap((row) => [
    Number(row.pur || 0) + Number(row.tin || 0),
    Number(row.sal || 0) + Number(row.tout || 0),
    Number(row.stk || 0)
  ]));

  return (
    <div className="movement-chart">
      {months.map((row) => {
        // Transfer in/out stay folded into the purchase/sales totals (same
        // underlying figures as before) - only the bar rendering is
        // simplified to one flat color per category instead of a two-tone
        // stacked segment.
        const pur = Number(row.pur || 0) + Number(row.tin || 0);
        const sal = Number(row.sal || 0) + Number(row.tout || 0);
        const stock = Number(row.stk || 0);
        return (
          <div className="movement-month" key={row.period}>
            <div className="movement-bars">
              <MovementBar segments={[{ value: pur, cls: 'pur' }]} max={maxValue} />
              <MovementBar segments={[{ value: sal, cls: 'sale' }]} max={maxValue} />
              <MovementBar segments={[{ value: stock, cls: 'stk' }]} max={maxValue} />
            </div>
            <strong>{row.period}</strong>
          </div>
        );
      })}
    </div>
  );
}

function MovementBar({ segments, max }) {
  const total = segments.reduce((sum, seg) => sum + seg.value, 0);
  const height = total > 0 ? Math.max(6, (total / max) * 100) : 0;
  return (
    <div className="movement-bar-set">
      <em>{total}</em>
      <div className="movement-bar-track">
        <div className="movement-bar-fill" style={{ height: `${height}%` }}>
          {segments.map((seg) => (seg.value > 0 ? (
            <div
              key={seg.cls}
              className={`movement-bar-segment ${seg.cls}`}
              style={{ height: `${(seg.value / total) * 100}%` }}
            />
          ) : null))}
        </div>
      </div>
    </div>
  );
}

function MovementLegend() {
  return (
    <div className="movement-legend">
      <span><i className="pur" />Purchase</span>
      <span><i className="tin" />Transfer In</span>
      <span><i className="sale" />Sales</span>
      <span><i className="tout" />Transfer Out</span>
      <span><i className="stk" />Stock</span>
    </div>
  );
}

function daysUntil(dateValue) {
  if (!dateValue) return null;
  const target = new Date(String(dateValue).slice(0, 10));
  if (Number.isNaN(target.getTime())) return null;
  return Math.round((target.getTime() - Date.now()) / 86400000);
}

function batchExpiryDate(row) {
  return row?.expiry_date || row?.expirydate || null;
}

function batchLastPurchaseDate(row) {
  return row?.last_purchase_date || row?.grndate || null;
}

function batchLastSaleDate(row) {
  return row?.last_sale_date || row?.lastsaledate || null;
}

const NEAR_EXPIRY_DAYS = 60;
// §6 business rule: Non Moving requires BOTH conditions - a batch that just
// arrived (< 10 days since purchase) hasn't had a fair chance to sell yet,
// so a long/absent sales age alone must not brand it dead stock. If either
// condition fails, Non Moving = NO - never derived from expiry alone.
const NON_MOVING_SALES_AGE_DAYS = 120;
const NON_MOVING_MIN_PURCHASE_AGE_DAYS = 10;

// Per-batch procurement-decision status. Expiry takes priority over
// dormancy since an about-to-expire batch is the more urgent risk even if
// it's still moving. Zero-stock batches can still be labelled (e.g. an
// expired zero-stock batch is genuinely "Expired") - they're simply
// excluded from PRODUCT-level aggregation (see summarizeProductBatches).
const BATCH_STATUS_META = {
  expired: { label: 'Expired', icon: '🔴', order: 0 },
  'near-expiry': { label: 'Near Expiry', icon: '🟠', order: 1 },
  'non-moving': { label: 'Non Moving', icon: '🟡', order: 2 },
  healthy: { label: 'Healthy', icon: '🟢', order: 3 }
};

function batchStatus(row) {
  const expiryDate = batchExpiryDate(row);
  const lastSaleDate = batchLastSaleDate(row);
  const lastPurchaseDate = batchLastPurchaseDate(row);
  const days = daysUntil(expiryDate);
  if (days !== null && days < 0) return 'expired';
  if (days !== null && days <= NEAR_EXPIRY_DAYS) return 'near-expiry';
  const stock = Number(row.stock) || 0;
  if (stock > 0) {
    const salesAge = lastSaleDate ? -daysUntil(lastSaleDate) : null;
    const purchaseAge = lastPurchaseDate ? -daysUntil(lastPurchaseDate) : null;
    // Never sold at all still counts as "sales age satisfied" - but only
    // once the batch itself has existed long enough (purchase age) to have
    // had a real chance to sell.
    const salesAgeOk = lastSaleDate == null || (salesAge !== null && salesAge >= NON_MOVING_SALES_AGE_DAYS);
    const purchaseAgeOk = purchaseAge !== null && purchaseAge >= NON_MOVING_MIN_PURCHASE_AGE_DAYS;
    if (salesAgeOk && purchaseAgeOk) return 'non-moving';
  }
  return 'healthy';
}

// §3: Priority 1 usable stock (Stock > 0) ahead of everything with none,
// then Near Expiry, then Expired, then Healthy/Non Moving - nearest expiry
// first, then largest stock first within the same tier.
const BATCH_SORT_RANK = { 'near-expiry': 0, expired: 1, 'non-moving': 2, healthy: 2 };

function sortedBatches(rows) {
  return [...rows].sort((a, b) => {
    const stockGroupA = (Number(a.stock) || 0) > 0 ? 0 : 1;
    const stockGroupB = (Number(b.stock) || 0) > 0 ? 0 : 1;
    if (stockGroupA !== stockGroupB) return stockGroupA - stockGroupB;
    const rankDiff = BATCH_SORT_RANK[batchStatus(a)] - BATCH_SORT_RANK[batchStatus(b)];
    if (rankDiff !== 0) return rankDiff;
    const expiryDateA = batchExpiryDate(a);
    const expiryDateB = batchExpiryDate(b);
    const expiryA = expiryDateA ? new Date(String(expiryDateA).slice(0, 10)).getTime() : Infinity;
    const expiryB = expiryDateB ? new Date(String(expiryDateB).slice(0, 10)).getTime() : Infinity;
    if (expiryA !== expiryB) return expiryA - expiryB;
    return (Number(b.stock) || 0) - (Number(a.stock) || 0);
  });
}

function expiryNoteFor(days) {
  if (days === null) return '';
  if (days < 0) return `Expired ${Math.abs(days)}d`;
  return `${days} Days`;
}

// §4/§5: Purchase Age / Sales Age display text + color tier, shared by both
// columns since the thresholds and formatting are identical.
function ageInfo(dateValue) {
  if (!dateValue) return { text: '-', tier: null };
  const days = -daysUntil(dateValue); // daysUntil is negative for past dates
  if (days === null || Number.isNaN(days)) return { text: '-', tier: null };
  const tier = days > 180 ? 'red' : days > 90 ? 'orange' : days >= 30 ? 'yellow' : 'green';
  return { text: `${days}`, tier };
}

function NonMovingHighlightCard({ nonMovingProducts, nonMovingLoading, nonMovingIndex, onPrev, onNext, onSearch, allStores, storeFilter, onStoreFilterChange }) {
  const storeFilterControl = allStores?.length ? (
    <select
      className="non-moving-store-filter"
      value={storeFilter || ''}
      onChange={(event) => onStoreFilterChange?.(event.target.value)}
      title="Filter non-moving stock to one store"
    >
      <option value="">All Stores</option>
      {allStores.map((store) => (
        <option key={store.store_id} value={store.store_id}>{store.store_name || store.store_code}</option>
      ))}
    </select>
  ) : null;

  if (!nonMovingProducts?.length) {
    return (
      <section className="non-moving-global-card">
        <div className="non-moving-wrap non-moving-wrap-empty">
          <div className="non-moving-header-box">
            <div className="non-moving-block-label">
              {'NON MOVING'.split('').map((char, index) => (
                <span key={index}>{char === ' ' ? ' ' : char}</span>
              ))}
            </div>
            <div className="non-moving-block-header">{storeFilterControl}</div>
          </div>
          <div className="non-moving-empty-body">
            {nonMovingLoading && <span className="non-moving-empty-spinner" aria-hidden="true" />}
            <span>{nonMovingLoading ? 'Loading non-moving stock…' : 'No non-moving stock found for this filter.'}</span>
          </div>
        </div>
      </section>
    );
  }

  const index = nonMovingIndex % nonMovingProducts.length;
  const product = nonMovingProducts[index];

  return (
    <section className="non-moving-global-card">
      <NonMovingDetailPanel
        product={product}
        onSearch={onSearch}
        storeFilterControl={storeFilterControl}
        nav={{
          index,
          total: nonMovingProducts.length,
          storeName: product?.__storeName,
          onPrev,
          onNext
        }}
      />
    </section>
  );
}

function nonMovingCost(product) {
  const stripQty = Number(product?.StripQty ?? 0);
  const stock = Number(product?.TotalStock ?? product?.Batch_Stock ?? 0);
  const unitCost = Number(product?.PurchasePrice ?? product?.PTR ?? 0);
  const mrp = Number(product?.MRP ?? 0);
  if (stripQty > 0 && unitCost > 0) return stripQty * unitCost;
  if (stock > 0 && unitCost > 0) return stock * unitCost;
  return stock * mrp;
}

function NonMovingDetailPanel({ product, onSearch, nav, storeFilterControl }) {
  const stock = Number(product.TotalStock ?? product.Batch_Stock ?? 0);
  const stripQty = Number(product.StripQty ?? 0);
  const mrp = Number(product.MRP ?? 0);
  const totalCost = nonMovingCost(product);
  const daysLeft = daysUntil(product.ExpiryDate);
  const expired = daysLeft !== null && daysLeft < 0;
  const nearExpiry = !expired && daysLeft !== null && daysLeft <= 60;
  const clickable = typeof onSearch === 'function';
  const expiryNote = expired
    ? `expired ${Math.abs(daysLeft)}d ago`
    : nearExpiry
      ? `expires in ${daysLeft}d`
      : null;

  return (
    <div className="non-moving-wrap">
      <div className="non-moving-header-box">
        <div className="non-moving-block-label">
          {'NON MOVING'.split('').map((char, index) => (
            <span key={index}>{char === ' ' ? ' ' : char}</span>
          ))}
        </div>
        <div className="non-moving-block-header">
          {nav && <span className="non-moving-block-position">({nav.index + 1}/{nav.total})</span>}
          <span className="non-moving-block-store">{nav?.storeName || ''}</span>
          {product.ProductName && (
            <>
              <span className="non-moving-block-sep">·</span>
              <span className="non-moving-block-product">{product.ProductName}</span>
            </>
          )}
          {nav && (
            <span className="non-moving-block-nav-buttons">
              <button type="button" className="non-moving-block-nav" onClick={nav.onPrev}>‹</button>
              <button type="button" className="non-moving-block-nav" onClick={nav.onNext}>›</button>
            </span>
          )}
          {storeFilterControl}
        </div>
      </div>
      <div
        className={`non-moving-panel-row ${expired ? 'expired' : nearExpiry ? 'near-expiry' : ''} ${clickable ? 'clickable' : ''}`}
        role={clickable ? 'button' : undefined}
        tabIndex={clickable ? 0 : undefined}
        title={clickable ? 'Search this product across all stores' : undefined}
        onClick={clickable ? () => onSearch(product.ProductName) : undefined}
        onKeyDown={clickable ? (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onSearch(product.ProductName); } } : undefined}
      >
        <div><span>Stock Cost</span><strong className="non-moving-value-highlight">{totalCost ? totalCost.toFixed(2) : '-'}</strong></div>
        <div className={expired ? 'expiry-dead' : nearExpiry ? 'expiry-highlight' : ''}>
          <span>Expiry</span>
          <strong>
            {formatDate(product.ExpiryDate)}
            {expiryNote && <em className="non-moving-expiry-note">{expiryNote}</em>}
          </strong>
        </div>
        <div><span>Stock Qty</span><strong>{stock}{stripQty > 0 ? ` (${stripQty} strips)` : ''}</strong></div>
        <div><span>PTR (Cost)</span><strong>{Number(product.PurchasePrice ?? product.PTR ?? 0) ? formatMoney(product.PurchasePrice ?? product.PTR) : '-'}</strong></div>
        <div><span>MRP</span><strong>{mrp ? formatMoney(mrp) : '-'}</strong></div>
        <div><span>Supplier</span><strong title={product.SupplierName || ''}>{product.SupplierName || '-'}</strong></div>
        <div><span>Last Received</span><strong>{formatDate(product.LastGRNDate)}</strong></div>
        <div><span>Last Sale</span><strong>{formatDate(product.LastBillDate)}</strong></div>
      </div>
    </div>
  );
}

function formatDate(value) {
  if (!value) return '-';
  const raw = String(value).slice(0, 10);
  const parts = raw.split('-');
  if (parts.length === 3) return `${parts[2]}/${parts[1]}/${parts[0].slice(2)}`;
  return raw;
}

const SUPPLIER_MAPPING_FILTERS = [
  { value: 'all', label: 'All products' },
  { value: 'not_mapped', label: 'Not mapped' },
  { value: 'partially_matched', label: 'Partially matched' },
  { value: 'fully_matched', label: 'Fully matched' }
];

function analysisBucketLabel(bucket) {
  return ({
    already_mapped: 'Already mapped',
    stores_not_mapped: 'Stores not mapped',
    mapped_store_no_stock: 'Mapped store no stock',
    home_store_no_stock_prediction: 'Predict new stock',
    not_mapped_products: 'Not mapped product'
  })[bucket] || bucket || '-';
}

function mappingFilterLabel(value) {
  return SUPPLIER_MAPPING_FILTERS.find((filter) => filter.value === value)?.label || 'Filtered';
}

function supplierRowStableKey(row) {
  return [
    String(row?.supplier_code || '').trim(),
    String(row?.supplier_product_code || '').trim(),
    String(row?.supplier_product_name || '').trim().toLowerCase()
  ].join('::');
}

function normalizeMappingScopeStatus(row) {
  if (row?.mapping_scope_status) return row.mapping_scope_status;
  const hasMapping = Boolean(Number(row?.has_mapping ?? (row?.product_code ? 1 : 0)));
  if (!hasMapping) return 'not_mapped';
  const unmappedStoreCount = Number(row?.unmapped_store_count ?? 0);
  return unmappedStoreCount > 0 ? 'partially_matched' : 'fully_matched';
}

function normalizeSupplierProductRow(row) {
  const hasMapping = Boolean(Number(row?.has_mapping ?? (row?.product_code ? 1 : 0)));
  return {
    ...row,
    has_mapping: hasMapping ? 1 : 0,
    mapping_scope_status: normalizeMappingScopeStatus(row),
    _stable_key: supplierRowStableKey(row)
  };
}

function normalizeSupplierProductRows(rows) {
  return asArray(rows).map(normalizeSupplierProductRow);
}

function SupplierStockAnalysis({ session, settings: settingsProp, tenants = [], onTenantChange }) {
  const settings = settingsProp || loadSettings();
  const tenantId = settings.tenantId || '';
  const storeId = settings.storeId || '';
  // Display-scope filter for the store/warehouse lists: '' = all tenants (super
  // admin only), else a tenant_id. Separate from settings.tenantId, which is the
  // actual query tenant and follows the selected warehouse (see effect below).
  const [tenantFilter, setTenantFilter] = useState(() => settings.tenantId || '');
  const [suppliers, setSuppliers] = useState([]);
  const [supplierSearch, setSupplierSearch] = useState('');
  const [supplierStatus, setSupplierStatus] = useState({ state: 'idle', message: 'Loading suppliers...' });
  const [selectedSupplier, setSelectedSupplier] = useState('');
  // Auto-hidden once a supplier is picked (see selectSupplier) so the product
  // list gets the width back; "Change Supplier" flips it on again without
  // touching any other state.
  const [showSupplierPanel, setShowSupplierPanel] = useState(true);

  const [products, setProducts] = useState([]);
  const [productSearch, setProductSearch] = useState('');
  const [onlyAvailable, setOnlyAvailable] = useState(true);
  const [mappingFilter, setMappingFilter] = useState('all');
  const [productStatus, setProductStatus] = useState({ state: 'idle', message: 'Select a supplier to list products.' });
  const [reportStatus, setReportStatus] = useState({ state: 'idle', message: '' });
  const [reportBusy, setReportBusy] = useState(false);
  // Keyboard nav (Up/Down/Enter/Esc, req 2) over the virtualized list below.
  const [highlightIndex, setHighlightIndex] = useState(-1);
  const productListScrollRef = useRef(null);
  const productRequestRef = useRef(null);
  // Monotonic guard so only the latest-initiated supplier load applies. Without
  // it, the initial all-stores query (fired before the warehouse resolves) can
  // resolve AFTER the warehouse-scoped query and clobber it with every store's
  // suppliers.
  const supplierRequestRef = useRef(0);
  // Session-visited-only 3rd/4th match state for the product list dot -
  // 'similar' | 'nomatch', keyed by supplier_stock_id. Populated lazily as
  // rows are opened (see loadSimilarSearch) rather than precomputed for the
  // whole list, which would mean running the cascade search for every
  // unmapped row before anyone asks - the opposite of req 11/12.
  const [rowMatchStates, setRowMatchStates] = useState({});

  const [selectedStockId, setSelectedStockId] = useState('');
  // Captured directly from the clicked row at selection time (not read back
  // off the network response) so Similar Search always has a name to work
  // with immediately, regardless of stockQuery timing.
  const [selectedProductName, setSelectedProductName] = useState('');
  const [activeDetailStore, setActiveDetailStore] = useState('');
  const [savingMapping, setSavingMapping] = useState(false);
  const queryClient = useQueryClient();

  const [allStores, setAllStores] = useState([]);
  // Supplier Stock Analysis is central (warehouse) ordering. Stores/warehouses
  // shown are scoped to tenantFilter ('' = all tenants). A store is a warehouse
  // when flagged is_warehouse (dbo.stores column), falling back to the legacy
  // 'NMW' code so this keeps working before the column is populated everywhere.
  const isWarehouse = (s) => Boolean(s?.is_warehouse) || isWarehouseStore(s);
  const scopedStores = useMemo(
    () => (tenantFilter ? allStores.filter((s) => String(s.tenant_id) === String(tenantFilter)) : allStores),
    [allStores, tenantFilter],
  );
  const warehouses = useMemo(() => scopedStores.filter(isWarehouse), [scopedStores]);
  const tenantNameById = useMemo(() => {
    const map = new Map();
    tenants.forEach((t) => map.set(String(t.tenant_id), t.tenant_name || t.tenant_code || ''));
    return map;
  }, [tenants]);
  const [warehouseId, setWarehouseId] = useState('');
  const selectedWarehouse = useMemo(() => {
    const found = warehouses.find((w) => w.store_id === warehouseId);
    if (found) return found;
    // In all-tenants mode (tenantFilter === '') the user must explicitly pick
    // which tenant's warehouse to order for — never auto-fall-back to the first
    // one. Scoped to a single tenant, auto-selecting its first warehouse is a
    // convenience, not a cross-tenant surprise.
    if (!tenantFilter) return null;
    return warehouses[0] || null;
  }, [warehouses, warehouseId, tenantFilter]);
  // Keep a valid warehouse selected as the list changes (tenant switch / load).
  useEffect(() => {
    if (!warehouses.length) { if (warehouseId) setWarehouseId(''); return; }
    // All-tenants mode: wait for an explicit pick; only drop a now-stale id.
    if (!tenantFilter) {
      if (warehouseId && !warehouses.some((w) => w.store_id === warehouseId)) setWarehouseId('');
      return;
    }
    if (!warehouses.some((w) => w.store_id === warehouseId)) setWarehouseId(warehouses[0].store_id);
  }, [warehouses, warehouseId, tenantFilter]);
  // The actual query tenant follows the selected warehouse's tenant, so every
  // downstream query stays scoped even in all-tenants mode without extra plumbing.
  useEffect(() => {
    const wtid = selectedWarehouse?.tenant_id;
    if (wtid && String(wtid) !== String(tenantId)) onTenantChange?.(wtid);
  }, [selectedWarehouse, tenantId, onTenantChange]);
  // The supplier/product list is scoped to the selected warehouse store.
  const scopeStoreId = selectedWarehouse?.store_id ?? '';
  // Suppliers are always warehouse-scoped, so a resolved warehouse is required
  // before loading — in every mode, not just all-tenants. Without this, a tenant
  // that has no warehouse (selectedWarehouse === null) would load with tenant_id
  // undefined and the API would fall back to the previously-queried tenant,
  // leaking another tenant's suppliers.
  const needWarehousePick = !selectedWarehouse;
  // { searchKey, matchesFound, storesWithMatches, byStore: Map(store_id -> {storeMeta, candidates[]}) }
  const [similar, setSimilar] = useState(null);
  const [similarStatus, setSimilarStatus] = useState({ state: 'idle', message: '' });
  const [similarDetails, setSimilarDetails] = useState({}); // store_id -> core detail (mirrors StockAvailability's storeDetails)
  const [exactFallbackDetails, setExactFallbackDetails] = useState({}); // store_id -> core detail for unresolved exact-grid stores
  const [selectedCandidate, setSelectedCandidate] = useState(null); // { storeId, product }
  const [similarSearchChars, setSimilarSearchChars] = useState(() => {
    const saved = Number(loadSettings().similarSearchChars || 6);
    return Math.min(12, Math.max(3, saved || 6));
  });

  const [importOpen, setImportOpen] = useState(false);
  const selectedStockIdRef = useRef('');
  const exactFallbackCacheRef = useRef(new Map());
  const [persistedAnalysisView, setPersistedAnalysisView] = useState(null);
  const recentAnalysisCacheRef = useRef(new Map());
  const [loadMetrics, setLoadMetrics] = useState({ stockMs: null, detailsMs: null, totalMs: null, selectionId: '', resolvedProductCode: '', cached: false });
  const selectionTimingRef = useRef({ selectionId: '', startedAt: 0, stockResolvedAt: 0, stockMs: null, detailsMs: null });
  const rowDetailKeyRef = useRef(new Map());
  const prefetchWindowTokenRef = useRef(0);
  useEffect(() => { selectedStockIdRef.current = selectedStockId; }, [selectedStockId]);

  const hideSupplierColumn = isSalesmanOnly(session);
  const visibility = historyVisibility(session);
  const [billDetail, setBillDetail] = useState(null);
  const [orderDrafts, setOrderDrafts] = useState({});
  const [remarkDrafts, setRemarkDrafts] = useState({});
  const [activeGridCell, setActiveGridCell] = useState('qty');
  const [exportStatus, setExportStatus] = useState({ state: 'idle', message: '' });
  const qtyRefs = useRef({});

  // Stage 1 (fast): match resolution + all-store stock in one batched query.
  // React Query gives cancellation (switching products aborts the previous
  // product's in-flight fetch via queryFn's signal) and caching (req 5, req 8)
  // for free, replacing the old dashboardCacheRef + selectedStockIdRef guards.
  const stockQuery = useQuery({
    queryKey: ['supplier-dashboard-stock', selectedStockId],
    queryFn: ({ signal }) => api.getSupplierDashboardStock(selectedStockId, session, { signal }),
    enabled: Boolean(selectedStockId)
  });
  const match = stockQuery.data || null;
  const productCode = match?.product_code || null;
  const sourceStoreId = match?.supplier_stock?.store_id || null;

  // Stage 2 (slower): batches/purchases/sales/movement history, only once
  // stage 1 resolved a product_code - streams in after the stock grid is
  // already visible instead of blocking it (req 4, 9, 11).
  const detailsQuery = useQuery({
    queryKey: ['supplier-dashboard-details', sourceStoreId, productCode, 4],
    queryFn: ({ signal }) => api.getSupplierDashboardDetails(selectedStockId, session, {
      signal, productCode, sourceStoreId, months: 4
    }),
    enabled: Boolean(selectedStockId) && Boolean(productCode) && Boolean(sourceStoreId)
  });

  const dashboard = useMemo(() => {
    if (!match?.dashboard) return null;
    return {
      ...match.dashboard,
      movement: detailsQuery.data?.movement || [],
      batches: detailsQuery.data?.batches || [],
      purchases: detailsQuery.data?.purchases || [],
      sales: detailsQuery.data?.sales || []
    };
  }, [match, detailsQuery.data]);

  useEffect(() => {
    if (!selectedStockId) return;
    selectionTimingRef.current = {
      selectionId: selectedStockId,
      startedAt: performance.now(),
      stockResolvedAt: 0,
      stockMs: null,
      detailsMs: null
    };
  }, [selectedStockId]);

  useEffect(() => {
    if (!selectedStockId || !stockQuery.data || selectionTimingRef.current.selectionId !== selectedStockId) return;
    if (selectionTimingRef.current.stockResolvedAt) return;
    const stockMs = performance.now() - selectionTimingRef.current.startedAt;
    selectionTimingRef.current.stockResolvedAt = performance.now();
    selectionTimingRef.current.stockMs = stockMs;
    if (!stockQuery.data.product_code) {
      setLoadMetrics({
        stockMs,
        detailsMs: null,
        totalMs: stockMs,
        selectionId: selectedStockId,
        resolvedProductCode: '',
        cached: stockQuery.isFetched && !stockQuery.isFetching && stockMs < 80
      });
    }
  }, [selectedStockId, stockQuery.data, stockQuery.isFetched, stockQuery.isFetching]);

  useEffect(() => {
    if (!selectedStockId || !match?.product_code || !dashboard || selectionTimingRef.current.selectionId !== selectedStockId) return;
    if (!selectionTimingRef.current.stockResolvedAt) {
      const stockMs = performance.now() - selectionTimingRef.current.startedAt;
      selectionTimingRef.current.stockResolvedAt = performance.now();
      selectionTimingRef.current.stockMs = stockMs;
    }
    const detailsMs = performance.now() - selectionTimingRef.current.stockResolvedAt;
    const totalMs = performance.now() - selectionTimingRef.current.startedAt;
    selectionTimingRef.current.detailsMs = detailsMs;
    setLoadMetrics({
      stockMs: selectionTimingRef.current.stockMs,
      detailsMs,
      totalMs,
      selectionId: selectedStockId,
      resolvedProductCode: match.product_code,
      cached: totalMs < 120
    });
    setPersistedAnalysisView({
      selectionId: selectedStockId,
      match,
      dashboard
    });
  }, [selectedStockId, match, dashboard]);

  useEffect(() => {
    if (!selectedStockId || !match) return;
    rememberRecentAnalysis(selectedStockId, {
      persistedAnalysisView: match.product_code && dashboard
        ? {
          selectionId: selectedStockId,
          match,
          dashboard
        }
        : null,
      similar,
      similarStatus,
      similarDetails,
      exactFallbackDetails,
      selectedCandidate,
      activeDetailStore
    });
  }, [
    selectedStockId,
    match,
    dashboard,
    similar,
    similarStatus,
    similarDetails,
    exactFallbackDetails,
    selectedCandidate,
    activeDetailStore
  ]);

  const detailStatus = useMemo(() => {
    if (!selectedStockId) return { state: 'idle', message: 'Select a product to analyze.' };
    if (stockQuery.isLoading) return { state: 'loading', message: 'Loading match and stock details...' };
    if (stockQuery.isError) return { state: 'error', message: stockQuery.error.message };
    if (match?.product_code) {
      return { state: 'ok', message: match.match_status === 'exact' ? 'Exact mapping found.' : 'Resolved from a saved mapping.' };
    }
    return { state: 'ok', message: 'No exact match. Searching similar products...' };
  }, [selectedStockId, stockQuery.isLoading, stockQuery.isError, stockQuery.error, match]);

  const detailsStage = detailsQuery.isLoading || (Boolean(productCode) && !detailsQuery.data)
    ? 'loading'
    : (detailsQuery.data ? 'done' : 'idle');

  function rememberRecentAnalysis(stockId, snapshot) {
    if (!stockId || !snapshot) return;
    const next = new Map(recentAnalysisCacheRef.current);
    next.delete(stockId);
    next.set(stockId, { ...snapshot, cachedAt: Date.now() });
    while (next.size > RECENT_ANALYSIS_ROWS) {
      const oldestKey = next.keys().next().value;
      next.delete(oldestKey);
    }
    recentAnalysisCacheRef.current = next;
  }

  function restoreRecentAnalysis(stockId) {
    const cached = recentAnalysisCacheRef.current.get(stockId);
    if (!cached) return false;
    if (cached.persistedAnalysisView) setPersistedAnalysisView(cached.persistedAnalysisView);
    setSimilar(cached.similar ?? null);
    setSimilarStatus(cached.similarStatus ?? { state: 'idle', message: '' });
    setSimilarDetails(cached.similarDetails ?? {});
    setExactFallbackDetails(cached.exactFallbackDetails ?? {});
    setSelectedCandidate(cached.selectedCandidate ?? null);
    if (cached.activeDetailStore) setActiveDetailStore(cached.activeDetailStore);
    setLoadMetrics((prev) => (
      cached.persistedAnalysisView?.selectionId === stockId
        ? { ...prev, selectionId: stockId, cached: true }
        : prev
    ));
    return true;
  }

  const showingPersistedAnalysis = Boolean(
    persistedAnalysisView?.dashboard
    && persistedAnalysisView.selectionId !== selectedStockId
    && (stockQuery.isFetching || detailsQuery.isFetching)
  );
  const renderedMatch = showingPersistedAnalysis ? persistedAnalysisView.match : match;
  const renderedDashboard = showingPersistedAnalysis ? persistedAnalysisView.dashboard : dashboard;

  // Cache Similar Search results (ranked candidates per store) by supplier_stock_id.
  const similarSearchCacheRef = useRef(new Map());
  // Cache per-candidate store detail ("storeId:productCode" -> core), mirrors
  // StockAvailability's detailCacheRef.
  const similarDetailCacheRef = useRef(new Map());

  useEffect(() => {
    // Clear any supplier/product selection when a super admin switches tenant.
    setSelectedSupplier('');
    setSelectedStockId('');
    setProducts([]);
    setShowSupplierPanel(true);
  }, [tenantId]);

  useEffect(() => {
    // Wait until the store list has loaded so the warehouse (scopeStoreId) is
    // resolved before the first fetch — otherwise the initial all-stores query
    // races (and can clobber) the warehouse-scoped one. Reloads on tenant switch
    // and once the warehouse id resolves.
    if (!allStores.length) return;
    if (needWarehousePick) {
      supplierRequestRef.current += 1; // supersede any in-flight load
      setSuppliers([]);
      setSelectedSupplier('');
      setProducts([]);
      setShowSupplierPanel(true);
      setSupplierStatus({
        state: 'idle',
        message: warehouses.length
          ? 'Select a warehouse to list its suppliers.'
          : 'No warehouse is configured for this tenant.',
      });
      return;
    }
    // Warehouse/tenant scope changed: drop any supplier picked under the old
    // store so a stale selection (a supplier not stocked at this warehouse)
    // can't linger and render an empty product list.
    setSelectedSupplier('');
    setSelectedStockId('');
    setProducts([]);
    loadSuppliers('');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId, scopeStoreId, allStores.length, needWarehousePick]);

  useEffect(() => {
    api.listStores(session).then((rows) => setAllStores(asArray(rows))).catch(() => setAllStores([]));
  }, [session]);

  useEffect(() => {
    // Gate on the store list too: this effect's timer closure captures the
    // current scopeStoreId, so running it before the warehouse resolves would
    // schedule a stale all-stores query that lands last. Re-runs (with a fresh
    // warehouse-scoped closure) once allStores loads.
    if (!allStores.length || needWarehousePick) return;
    const timer = setTimeout(() => loadSuppliers(supplierSearch), 200);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [supplierSearch, allStores.length, scopeStoreId, needWarehousePick]);

  // Products are fetched (and cached) once per supplier only - search and
  // "in stock only" are pure client-side filters below, so toggling them
  // never re-triggers a network call or a loading indicator.
  useEffect(() => {
    if (!selectedSupplier) { setProducts([]); return; }
    loadProducts(selectedSupplier);
  }, [selectedSupplier]);

  useEffect(() => {
    if (!selectedSupplier) {
      setOrderDrafts({});
      setRemarkDrafts({});
      return;
    }
    const draft = loadProcurementDrafts(tenantId, storeId, selectedSupplier);
    setOrderDrafts(draft.qty);
    setRemarkDrafts(draft.remarks);
  }, [tenantId, storeId, selectedSupplier]);

  useEffect(() => {
    if (!selectedSupplier) return;
    saveProcurementDrafts(tenantId, storeId, selectedSupplier, orderDrafts, remarkDrafts);
  }, [tenantId, storeId, selectedSupplier, orderDrafts, remarkDrafts]);

  // Instant client-side narrowing of the already-fetched product list (req 3,
  // req 16: <100ms) - covers both text search and the "in stock only" toggle.
  const mappingFilteredProducts = useMemo(() => {
    return products.filter((row) => (
      mappingFilter === 'all' || row.mapping_scope_status === mappingFilter
    ));
  }, [products, mappingFilter]);

  const visibleProducts = useMemo(() => {
    const term = productSearch.trim().toLowerCase();
    return mappingFilteredProducts.filter((row) => {
      const shouldApplyStockOnly = onlyAvailable && mappingFilter !== 'not_mapped';
      if (shouldApplyStockOnly && !(Number(row.available_stock) > 0)) return false;
      if (!term) return true;
      return String(row.supplier_product_name || '').toLowerCase().includes(term)
        || String(row.supplier_product_code || '').toLowerCase().includes(term)
        || String(row.product_code || '').toLowerCase().includes(term);
    });
  }, [mappingFilteredProducts, productSearch, onlyAvailable]);

  const filteredOutByStockOnly = mappingFilteredProducts.length > 0 && visibleProducts.length === 0 && onlyAvailable;

  useEffect(() => {
    if (!visibleProducts.length) {
      setSelectedStockId('');
      return;
    }
    if (!visibleProducts.some((row) => row.supplier_stock_id === selectedStockId)) {
      setSelectedStockId(visibleProducts[0].supplier_stock_id);
    }
  }, [visibleProducts, selectedStockId]);

  useEffect(() => { setHighlightIndex(visibleProducts.length ? 0 : -1); }, [visibleProducts]);

  // req 7: only visible rows are ever mounted, regardless of list size.
  const rowVirtualizer = useVirtualizer({
    count: visibleProducts.length,
    getScrollElement: () => productListScrollRef.current,
    estimateSize: () => 52,
    overscan: 10
  });

  function handleProductSearchKeyDown(event) {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setHighlightIndex((prev) => {
        const next = Math.min((prev < 0 ? -1 : prev) + 1, visibleProducts.length - 1);
        rowVirtualizer.scrollToIndex(next, { align: 'auto' });
        return next;
      });
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setHighlightIndex((prev) => {
        const next = Math.max((prev < 0 ? 0 : prev) - 1, 0);
        rowVirtualizer.scrollToIndex(next, { align: 'auto' });
        return next;
      });
    } else if (event.key === 'Enter') {
      event.preventDefault();
      const row = visibleProducts[highlightIndex];
      if (row) selectProduct(row);
    } else if (event.key === 'Escape') {
      event.preventDefault();
      setProductSearch('');
    }
  }

  async function prefetchProductRow(row) {
    if (!row?.supplier_stock_id) return null;
    const stockKey = ['supplier-dashboard-stock', row.supplier_stock_id];
    const stock = await queryClient.fetchQuery({
      queryKey: stockKey,
      queryFn: ({ signal }) => api.getSupplierDashboardStock(row.supplier_stock_id, session, { signal }),
      staleTime: 8 * 60 * 1000
    }).catch(() => null);
    if (!stock?.product_code || !stock?.supplier_stock?.store_id) return null;
    const detailKey = ['supplier-dashboard-details', stock.supplier_stock.store_id, stock.product_code, 4];
    rowDetailKeyRef.current.set(row.supplier_stock_id, detailKey);
    await queryClient.prefetchQuery({
      queryKey: detailKey,
      queryFn: ({ signal }) => api.getSupplierDashboardDetails(row.supplier_stock_id, session, {
        signal,
        productCode: stock.product_code,
        sourceStoreId: stock.supplier_stock.store_id,
        months: 4
      }),
      staleTime: 8 * 60 * 1000
    }).catch(() => null);
    return detailKey;
  }

  async function prefetchProductWindow(centerIndex) {
    if (!visibleProducts.length || centerIndex < 0) return;
    const token = ++prefetchWindowTokenRef.current;
    const start = Math.max(0, centerIndex - PREFETCH_PREVIOUS_ROWS);
    const end = Math.min(visibleProducts.length, centerIndex + PREFETCH_NEXT_ROWS + 1);
    const windowRows = visibleProducts.slice(start, end);
    const keepIds = new Set(windowRows.map((row) => row.supplier_stock_id));
    Array.from(recentAnalysisCacheRef.current.keys()).forEach((stockId) => keepIds.add(stockId));

    for (let offset = 0; offset < windowRows.length; offset += PREFETCH_CONCURRENCY) {
      if (prefetchWindowTokenRef.current !== token) return;
      const batch = windowRows.slice(offset, offset + PREFETCH_CONCURRENCY);
      await Promise.all(batch.map((row) => prefetchProductRow(row)));
    }

    if (prefetchWindowTokenRef.current !== token) return;

    visibleProducts.forEach((row) => {
      if (!row?.supplier_stock_id || keepIds.has(row.supplier_stock_id)) return;
      queryClient.removeQueries({ queryKey: ['supplier-dashboard-stock', row.supplier_stock_id], exact: true });
      const detailKey = rowDetailKeyRef.current.get(row.supplier_stock_id);
      if (detailKey) {
        queryClient.removeQueries({ queryKey: detailKey, exact: true });
        rowDetailKeyRef.current.delete(row.supplier_stock_id);
      }
    });
  }

  function prefetchAdjacentProducts(index) {
    prefetchProductWindow(index).catch(() => {});
  }

  const groups = useMemo(() => (renderedDashboard ? groupDashboardByStore(renderedDashboard) : []), [renderedDashboard]);

  useEffect(() => {
    if (!visibleProducts.length) return;
    const selectedIndex = visibleProducts.findIndex((row) => row.supplier_stock_id === selectedStockId);
    const centerIndex = selectedIndex >= 0 ? selectedIndex : 0;
    prefetchProductWindow(centerIndex).catch(() => {});
  }, [visibleProducts, selectedStockId]);

  // Default the store-detail tab to this device's home store whenever a new
  // product's stores load; keep the current tab if it still applies (e.g.
  // the user already picked a store and the next product also stocks there).
  useEffect(() => {
    if (!groups.length) return;
    const loginStoreId = session?.user?.roles?.[0]?.store_id;
    setActiveDetailStore((prev) => {
      if (groups.some((group) => group.store.store_id === prev)) return prev;
      if (loginStoreId && groups.some((group) => group.store.store_id === loginStoreId)) return loginStoreId;
      return groups[0].store.store_id;
    });
  }, [groups, session]);

  const activeSupplierProductName = selectedProductName || renderedMatch?.supplier_stock?.supplier_product_name || '';

  useEffect(() => {
    if (!selectedStockId || !match || match.product_code || !activeSupplierProductName) return;
    loadSimilarSearch(selectedStockId, activeSupplierProductName);
  }, [similarSearchChars, selectedStockId, match, activeSupplierProductName]);

  async function loadSuppliers(search) {
    const token = ++supplierRequestRef.current;
    setSupplierStatus({ state: 'loading', message: 'Loading suppliers...' });
    try {
      // Scope the supplier list to the selected warehouse store: each warehouse
      // has its own imported supplier stock (procurement.supplier_stock is keyed
      // by store_id), so the list must reflect that warehouse, not the whole
      // tenant. tenant_id is passed explicitly so it always matches the store.
      const response = await api.getSuppliers(session, { search, storeId: scopeStoreId, tenantId: selectedWarehouse?.tenant_id });
      if (supplierRequestRef.current !== token) return; // superseded by a newer load
      const items = asArray(response);
      setSuppliers(items);
      setSupplierStatus({ state: 'ok', message: items.length ? `${items.length} supplier(s).` : 'No suppliers found. Import an Excel sheet to begin.' });
    } catch (error) {
      if (supplierRequestRef.current !== token) return;
      setSuppliers([]);
      setSupplierStatus({ state: 'error', message: error.message });
    }
  }

  async function loadProducts(supplierCode) {
    // Guards against races when the user switches supplier again before this
    // call finishes - only the response for the still-selected supplier is
    // allowed to touch state.
    const requestToken = Symbol(supplierCode);
    productRequestRef.current = requestToken;
    const tenantId = loadSettings().tenantId;

    const cached = await getCachedProducts(tenantId, supplierCode);
    if (productRequestRef.current !== requestToken) return;
    if (cached.length) {
      setProducts(normalizeSupplierProductRows(cached));
      setProductStatus({ state: 'ok', message: `${cached.length} items (cached, refreshing...)` });
    } else {
      setProductStatus({ state: 'loading', message: 'Loading supplier products...' });
    }

    try {
      // Always fetch the full unfiltered set - search/in-stock filtering
      // happens client-side in visibleProducts, and the full set is what
      // gets cached and diffed against next time.
      // Scoped to the selected warehouse store (see loadSuppliers).
      const response = await api.getSupplierProducts(supplierCode, session, { search: '', onlyAvailable: 0, storeId: scopeStoreId, tenantId: selectedWarehouse?.tenant_id || tenantId });
      if (productRequestRef.current !== requestToken) return;
      const items = normalizeSupplierProductRows(response);
      setProducts(items);
      setProductStatus({ state: 'ok', message: `${items.length} items` });
      syncCachedProducts(tenantId, supplierCode, items);
    } catch (error) {
      if (productRequestRef.current !== requestToken) return;
      if (!cached.length) setProducts([]);
      setProductStatus({ state: 'error', message: error.message });
    }
  }

  function selectSupplier(code) {
    setSelectedSupplier(code);
    setShowSupplierPanel(!code);
    setSelectedStockId('');
    setSelectedProductName('');
    setSimilar(null);
    setSimilarStatus({ state: 'idle', message: '' });
    setSimilarDetails({});
    setSelectedCandidate(null);
    setActiveDetailStore('');
  }

  function handleSimilarSearchCharsChange(event) {
    const next = Math.min(12, Math.max(3, Number(event.target.value) || 6));
    setSimilarSearchChars(next);
    saveSettings({ ...loadSettings(), similarSearchChars: next });
  }

  function markRowMatchState(stockId, hasMatches) {
    setRowMatchStates((prev) => ({ ...prev, [stockId]: hasMatches ? 'similar' : 'nomatch' }));
  }

  function similarSummaryMessage(result) {
    return result.matchesFound
      ? `${result.matchesFound} similar product(s) found across ${result.storesWithMatches} store(s).`
      : 'No similar products found in any store.';
  }

  async function loadSimilarStoreCore(storeId, product) {
    const cacheKey = `${storeId}:${product.product_code}`;
    const cached = similarDetailCacheRef.current.get(cacheKey);
    if (cached) return cached;
    const result = await api.getStockCore(storeId, product.product_code, session, { months: 4 });
    const core = {
      product,
      batches: asArray(result?.batches),
      purchases: asArray(result?.purchases),
      sales: asArray(result?.sales),
      movement: asArray(result?.movement),
      billItems: []
    };
    if (core.batches.length || core.purchases.length || core.sales.length || core.movement.length) {
      similarDetailCacheRef.current.set(cacheKey, core);
    }
    return core;
  }

  // Auto-load each store's top-ranked candidate detail so StoreDataRow's
  // "pending" skeleton (which only resolves once `detail` stops being
  // undefined) never spins forever - mirrors StockAvailability's own
  // auto-fetch of products[0] in runSearch.
  function autoLoadTopCandidates(stockId, result) {
    result.byStore.forEach((entry, storeId) => {
      const top = entry.candidates[0];
      if (!top) return;
      loadSimilarStoreCore(storeId, top)
        .then((core) => {
          if (selectedStockIdRef.current !== stockId) return;
          setSimilarDetails((prev) => ({ ...prev, [storeId]: core }));
        })
        .catch(() => {
          if (selectedStockIdRef.current !== stockId) return;
          setSimilarDetails((prev) => ({ ...prev, [storeId]: null }));
        });
    });
  }

  async function loadSimilarSearch(stockId, supplierProductName) {
    const cacheKey = `${stockId}:${similarSearchChars}`;
    const cached = similarSearchCacheRef.current.get(cacheKey);
    if (cached) {
      if (!cached.matchesFound || !cached.byStore?.size) {
        similarSearchCacheRef.current.delete(cacheKey);
      } else {
        setSimilar(cached);
        setSimilarStatus({
          state: 'ok',
          message: `${similarSummaryMessage(cached)} Fallback search used ${cached.searchKey || '-'} (${similarSearchChars} chars).`
        });
        markRowMatchState(stockId, cached.matchesFound > 0);
        autoLoadTopCandidates(stockId, cached);
        return;
      }
    }

    setSimilarStatus({ state: 'loading', message: 'Searching similar products across stores...' });
    try {
      const searchKey = buildPrefixSearchKey(supplierProductName, similarSearchChars);
      if (!searchKey) {
        const empty = { searchKey: '', matchesFound: 0, storesWithMatches: 0, byStore: new Map() };
        if (selectedStockIdRef.current !== stockId) return;
        setSimilar(empty);
        setSimilarStatus({ state: 'ok', message: 'No similar products found.' });
        markRowMatchState(stockId, false);
        return;
      }
      const searchResponse = await api.searchStockProducts(searchKey, session, { onlyStock: false }).catch(() => null);
      if (selectedStockIdRef.current !== stockId) return;

      const storeStepHits = new Map();
      asArray(searchResponse?.stores).forEach((store) => {
        const list = store.products || [];
        if (!list.length) return;
        storeStepHits.set(store.store_id, { stepIndex: 0, products: list, storeMeta: store });
      });

      if (!storeStepHits.size) {
        const empty = { searchKey, matchesFound: 0, storesWithMatches: 0, byStore: new Map() };
        setSimilar(empty);
        setSimilarStatus({ state: 'ok', message: `No similar products found in any store for "${searchKey}".` });
        markRowMatchState(stockId, false);
        return;
      }

      // Rank each hit store's candidates against the ORIGINAL full supplier
      // name via the real matching engine (existing /api/product-mapping
      // endpoint - Name/Brand/Strength/Form/MRP weighted scoring), in parallel.
      const storeIds = Array.from(storeStepHits.keys());
      const rankedResponses = await Promise.all(
        storeIds.map((storeId) => api.getMatchCandidates(storeId, supplierProductName, session, { limit: 8 }).catch(() => null))
      );
      if (selectedStockIdRef.current !== stockId) return;

      const byStore = new Map();
      let matchesFound = 0;
      storeIds.forEach((storeId, index) => {
        const hit = storeStepHits.get(storeId);
        const stockByCode = new Map(hit.products.map((p) => [String(p.product_code), p]));
        const ranked = rankedResponses[index];
        let candidates;
        if (Array.isArray(ranked) && ranked.length) {
          candidates = ranked.map((c) => {
            const stockRow = stockByCode.get(String(c.target_product_code));
            const matchMeta = candidateMatchMeta(supplierProductName, c.target_product_name, c.total_score);
            return {
              product_code: c.target_product_code,
              product_name: c.target_product_name,
              sale_unit: stockRow?.sale_unit,
              stock: stockRow?.stock,
              mrp: c.mrp ?? stockRow?.mrp,
              score: c.total_score,
              matchPriority: matchMeta.priority,
              matchBadge: matchMeta.badge
            };
          });
        } else {
          // Ranking call failed for this store - fall back to the raw,
          // unranked stock-search hits rather than dropping the store.
          candidates = hit.products.map((p) => {
            const matchMeta = candidateMatchMeta(supplierProductName, p.product_name, 0);
            return {
              ...p,
              score: 0,
              matchPriority: matchMeta.priority,
              matchBadge: matchMeta.priority > 0
                ? matchMeta.badge
                : { label: 'SIM', className: 'similar', title: 'Similar match' }
            };
          });
        }
        candidates.sort((a, b) => {
          const priorityDiff = (b.matchPriority || 0) - (a.matchPriority || 0);
          if (priorityDiff !== 0) return priorityDiff;
          return (b.score || 0) - (a.score || 0);
        });
        matchesFound += candidates.length;
        byStore.set(storeId, { storeMeta: hit.storeMeta, candidates });
      });

      const result = { searchKey, matchesFound, storesWithMatches: byStore.size, byStore };
      similarSearchCacheRef.current.set(cacheKey, result);
      setSimilar(result);
      setSimilarStatus({
        state: 'ok',
        message: `${similarSummaryMessage(result)} Fallback search used ${searchKey} (${similarSearchChars} chars).`
      });
      markRowMatchState(stockId, matchesFound > 0);
      autoLoadTopCandidates(stockId, result);
    } catch (error) {
      if (selectedStockIdRef.current !== stockId) return;
      setSimilarStatus({ state: 'error', message: error.message });
    }
  }

  function selectSimilarCandidate(storeId, product) {
    setSelectedCandidate({ storeId, product });
    loadSimilarStoreCore(storeId, product)
      .then((core) => setSimilarDetails((prev) => ({ ...prev, [storeId]: core })))
      .catch(() => {});
  }

  // Selection itself is now just a state flip (<50ms, req 16) - the two
  // staged useQuery calls above react to selectedStockId changing, fetch,
  // cache, and cancel the previous product's in-flight requests on their own.
  function selectProduct(row) {
    const stockId = row.supplier_stock_id;
    setSelectedStockId(stockId);
    setSelectedProductName(row.supplier_product_name || '');
    const restored = restoreRecentAnalysis(stockId);
    if (!restored) {
      setSimilarDetails({});
      setExactFallbackDetails({});
      setSelectedCandidate(null);
      setSimilar(null);
      setSimilarStatus({ state: 'idle', message: '' });
    }
    const index = visibleProducts.findIndex((item) => item.supplier_stock_id === stockId);
    if (index >= 0) {
      setHighlightIndex(index);
      prefetchAdjacentProducts(index);
    }
  }

  function updateOrderQty(stockId, value) {
    setOrderDrafts((prev) => ({ ...prev, [stockId]: sanitizeOrderQty(value) }));
  }

  function focusGridCell(stockId, cell) {
    const ref = qtyRefs.current[stockId];
    if (ref?.focus) {
      ref.focus();
      if (ref.select) ref.select();
    }
  }

  function moveGridSelection(currentStockId, direction, cell = activeGridCell) {
    const index = visibleProducts.findIndex((row) => row.supplier_stock_id === currentStockId);
    if (index < 0) return;
    const nextIndex = Math.min(Math.max(index + direction, 0), visibleProducts.length - 1);
    const nextRow = visibleProducts[nextIndex];
    if (!nextRow) return;
    selectProduct(nextRow);
    setActiveGridCell(cell);
    requestAnimationFrame(() => focusGridCell(nextRow.supplier_stock_id, cell));
  }

  function exportOrderedRows() {
    if (!selectedSupplier) return;
    const orderedRows = visibleProducts
      .map((row) => ({
        row,
        qty: parseOrderQty(orderDrafts[row.supplier_stock_id])
      }))
      .filter(({ qty }) => qty > 0);
    if (!orderedRows.length) {
      setExportStatus({ state: 'error', message: 'No products with Order Qty > 0 to export.' });
      return;
    }
    const header = [
      'Supplier Product Code',
      'Internal Product Code',
      'Supplier Product Name',
      'Internal Product Name',
      'Order Qty',
      'Remarks',
      'Offer',
      'MRP',
      'PTR',
      'GST'
    ];
    const rows = orderedRows.map(({ row, qty }) => [
      row.supplier_product_code || '',
      row.product_code || '',
      row.supplier_product_name || '',
      row.mapped_product_name || '',
      qty,
      remarkDrafts[row.supplier_stock_id] || '',
      offerBadge(row),
      row.mrp ?? '',
      row.ptr ?? '',
      row.gst ?? ''
    ]);
    const csv = [header, ...rows].map((line) => line.map(csvCell).join(',')).join('\n');
    downloadTextFile(
      `procurement_${selectedSupplier}_${new Date().toISOString().slice(0, 10)}.csv`,
      csv,
      'text/csv;charset=utf-8'
    );
    setExportStatus({ state: 'ok', message: `Exported ${orderedRows.length} ordered row(s).` });
  }

  async function exportAnalysisReport() {
    if (!selectedSupplier || reportBusy) return;
    setReportBusy(true);
    setReportStatus({ state: 'loading', message: 'Building supplier analysis report...' });
    try {
      const response = await api.getSupplierAnalysisReport(selectedSupplier, session, {
        onlyAvailable: onlyAvailable ? 1 : 0
      });
      const rows = asArray(response?.rows);
      const visibleIds = new Set(visibleProducts.map((row) => row.supplier_stock_id));
      const visibleStableKeys = new Set(visibleProducts.map((row) => row._stable_key || supplierRowStableKey(row)));
      const filteredRows = rows.filter((row) => (
        visibleIds.has(row.supplier_stock_id)
        || visibleStableKeys.has(supplierRowStableKey(row))
      ));
      if (!filteredRows.length) {
        const fallbackRows = visibleProducts.map((row) => ({
          supplier_product_code: row.supplier_product_code || '',
          supplier_product_name: row.supplier_product_name || '',
          product_code: row.product_code || '',
          mapped_product_name: row.mapped_product_name || '',
          mapping_scope_status: row.mapping_scope_status || '',
          analysis_bucket: row.mapping_scope_status === 'not_mapped' ? 'not_mapped_products' : '',
          source_store_name: row.store_name || '',
          source_store_code: row.store_code || '',
          supplier_available_stock: row.available_stock ?? 0,
          source_store_stock_qty: '',
          network_stock_qty: '',
          mapped_store_count: row.mapped_store_count ?? '',
          unmapped_store_count: row.unmapped_store_count ?? '',
          stores_with_stock_count: '',
          stores_without_stock_count: '',
          recent_3m_sale_qty: '',
          avg_monthly_sale_qty: '',
          predicted_required_qty: '',
          ptr: row.ptr ?? '',
          mrp: row.mrp ?? ''
        }));
        if (!fallbackRows.length) {
          setReportStatus({ state: 'error', message: 'No rows match the current filters for analysis export.' });
          return;
        }
        const header = [
          'Supplier Product Code',
          'Supplier Product Name',
          'Mapped Product Code',
          'Mapped Product Name',
          'Filter Status',
          'Analysis Bucket',
          'Source Store',
          'Supplier Available Stock',
          'Source Store Stock',
          'Network Stock',
          'Mapped Store Count',
          'Unmapped Store Count',
          'Stores With Stock',
          'Stores Without Stock',
          'Recent 3M Sale Qty',
          'Avg Monthly Sale Qty',
          'Predicted Required New Stock',
          'PTR',
          'MRP'
        ];
        const csvRows = fallbackRows.map((row) => [
          row.supplier_product_code || '',
          row.supplier_product_name || '',
          row.product_code || '',
          row.mapped_product_name || '',
          row.mapping_scope_status || '',
          analysisBucketLabel(row.analysis_bucket),
          row.source_store_name || row.source_store_code || '',
          row.supplier_available_stock ?? 0,
          row.source_store_stock_qty ?? '',
          row.network_stock_qty ?? '',
          row.mapped_store_count ?? '',
          row.unmapped_store_count ?? '',
          row.stores_with_stock_count ?? '',
          row.stores_without_stock_count ?? '',
          row.recent_3m_sale_qty ?? '',
          row.avg_monthly_sale_qty ?? '',
          row.predicted_required_qty ?? '',
          row.ptr ?? '',
          row.mrp ?? ''
        ]);
        const csv = [header, ...csvRows].map((line) => line.map(csvCell).join(',')).join('\n');
        downloadTextFile(
          `supplier_analysis_${selectedSupplier}_${new Date().toISOString().slice(0, 10)}.csv`,
          csv,
          'text/csv;charset=utf-8'
        );
        setReportStatus({
          state: 'ok',
          message: `Exported ${fallbackRows.length} analysis row(s) using the current filtered grid data.`
        });
        return;
      }
      const header = [
        'Supplier Product Code',
        'Supplier Product Name',
        'Mapped Product Code',
        'Mapped Product Name',
        'Filter Status',
        'Analysis Bucket',
        'Source Store',
        'Supplier Available Stock',
        'Source Store Stock',
        'Network Stock',
        'Mapped Store Count',
        'Unmapped Store Count',
        'Stores With Stock',
        'Stores Without Stock',
        'Recent 3M Sale Qty',
        'Avg Monthly Sale Qty',
        'Predicted Required New Stock',
        'PTR',
        'MRP'
      ];
      const csvRows = filteredRows.map((row) => [
        row.supplier_product_code || '',
        row.supplier_product_name || '',
        row.product_code || '',
        row.mapped_product_name || '',
        row.mapping_scope_status || '',
        analysisBucketLabel(row.analysis_bucket),
        row.source_store_name || row.source_store_code || '',
        row.supplier_available_stock ?? 0,
        row.source_store_stock_qty ?? 0,
        row.network_stock_qty ?? 0,
        row.mapped_store_count ?? 0,
        row.unmapped_store_count ?? 0,
        row.stores_with_stock_count ?? 0,
        row.stores_without_stock_count ?? 0,
        row.recent_3m_sale_qty ?? 0,
        row.avg_monthly_sale_qty ?? 0,
        row.predicted_required_qty ?? 0,
        row.ptr ?? '',
        row.mrp ?? ''
      ]);
      const csv = [header, ...csvRows].map((line) => line.map(csvCell).join(',')).join('\n');
      downloadTextFile(
        `supplier_analysis_${selectedSupplier}_${new Date().toISOString().slice(0, 10)}.csv`,
        csv,
        'text/csv;charset=utf-8'
      );
      setReportStatus({
        state: 'ok',
        message: `Exported ${filteredRows.length} analysis row(s). Predicted new stock total: ${response?.summary?.predicted_required_qty ?? 0}.`
      });
    } catch (error) {
      setReportStatus({ state: 'error', message: error.message });
    } finally {
      setReportBusy(false);
    }
  }

  async function confirmMapping(productCode) {
    if (!match?.supplier_stock) return;
    const row = match.supplier_stock;
    setSavingMapping(true);
    try {
      await api.updateSupplierMapping({
        tenant_id: row.tenant_id,
        store_id: row.store_id,
        supplier_code: row.supplier_code,
        supplier_product_code: row.supplier_product_code,
        supplier_product_name: row.supplier_product_name,
        product_code: productCode,
        username: session?.user?.username || session?.user?.name
      }, session);
      // Mapping changed - stale cache entries must not win next select.
      queryClient.invalidateQueries({ queryKey: ['supplier-dashboard-stock'] });
      queryClient.invalidateQueries({ queryKey: ['supplier-dashboard-details'] });
      Array.from(similarSearchCacheRef.current.keys()).forEach((key) => {
        if (String(key).startsWith(`${selectedStockId}:`)) similarSearchCacheRef.current.delete(key);
      });
      setSimilar(null);
      setSelectedCandidate(null);
      if (selectedSupplier) loadProducts(selectedSupplier);
    } catch (error) {
      window.alert(error.message);
    } finally {
      setSavingMapping(false);
    }
  }

  const loginStoreId = session?.user?.roles?.[0]?.store_id;
  const similarGridStores = similar
    ? orderStores(scopedStores.length ? scopedStores : Array.from(similar.byStore.values()).map((entry) => entry.storeMeta), loginStoreId, [])
    : [];

  const exactGridStores = useMemo(() => {
    const storeOrder = loadSettings().storeOrder || [];
    return orderStores(groups.map((group) => group.store), loginStoreId, storeOrder);
  }, [groups, loginStoreId]);

  useEffect(() => {
    if (!selectedStockId || !activeSupplierProductName || !exactGridStores.length) {
      setExactFallbackDetails({});
      return;
    }
    const groupMap = new Map(groups.map((group) => [group.store.store_id, group]));
    const unresolvedStores = exactGridStores.filter((store) => groupMap.get(store.store_id)?.store?.store_match_status === 'unresolved');
    if (!unresolvedStores.length) {
      setExactFallbackDetails({});
      return;
    }

    let cancelled = false;
    const normalizedName = buildBrandKey(activeSupplierProductName) || activeSupplierProductName;
    const searchKey = buildPrefixSearchKey(activeSupplierProductName, similarSearchChars);
    const fallbackCacheKey = `${sourceStoreId || 'source'}:${renderedDashboard?.product_code || 'none'}:${similarSearchChars}`;

    async function resolveUnmappedStores() {
      const cached = exactFallbackCacheRef.current.get(fallbackCacheKey);
      if (cached) {
        setExactFallbackDetails(cached);
        return;
      }
      const entries = await Promise.all(unresolvedStores.map(async (store) => {
        let candidate = null;

        const ranked = await api.getMatchCandidates(store.store_id, normalizedName, session, { limit: 5 }).catch(() => null);
        if (Array.isArray(ranked) && ranked.length) {
          const top = [...ranked].sort((a, b) => {
            const matchA = candidateMatchMeta(activeSupplierProductName, a.target_product_name, a.total_score);
            const matchB = candidateMatchMeta(activeSupplierProductName, b.target_product_name, b.total_score);
            const priorityDiff = matchB.priority - matchA.priority;
            if (priorityDiff !== 0) return priorityDiff;
            return (b.total_score || 0) - (a.total_score || 0);
          })[0];
          const matchMeta = candidateMatchMeta(activeSupplierProductName, top.target_product_name, top.total_score);
          candidate = {
            product_code: top.target_product_code,
            product_name: top.target_product_name,
            sale_unit: '-',
            stock: 0,
            mrp: top.mrp,
            score: top.total_score,
            matchPriority: matchMeta.priority,
            matchBadge: matchMeta.priority > 0
              ? matchMeta.badge
              : {
                label: `${Math.round(top.total_score || 0)}%`,
                className: 'similar',
                title: `Normalized fallback: ${normalizedName}`
              }
          };
        }

        if (!candidate && searchKey) {
          const searchResponse = await api.searchStockProducts(searchKey, session, { onlyStock: false }).catch(() => null);
          const storeHit = asArray(searchResponse?.stores).find((row) => row.store_id === store.store_id);
          const top = [...(storeHit?.products || [])].sort((a, b) => {
            const matchA = candidateMatchMeta(activeSupplierProductName, a.product_name, 0);
            const matchB = candidateMatchMeta(activeSupplierProductName, b.product_name, 0);
            return matchB.priority - matchA.priority;
          })[0];
          if (top) {
            const matchMeta = candidateMatchMeta(activeSupplierProductName, top.product_name, 0);
            candidate = {
              ...top,
              matchPriority: matchMeta.priority,
              matchBadge: matchMeta.priority > 0
                ? matchMeta.badge
                : {
                  label: 'SIM',
                  className: 'similar',
                  title: `Normalized fallback: ${searchKey}`
                }
            };
          }
        }

        if (!candidate) return [store.store_id, null];

        const core = await loadSimilarStoreCore(store.store_id, candidate).catch(() => null);
        if (!core) {
          return [store.store_id, {
            product: candidate,
            movement: [],
            batches: [],
            purchases: [],
            sales: [],
            billItems: []
          }];
        }

        return [store.store_id, {
          ...core,
          product: {
            ...core.product,
            matchBadge: candidate.matchBadge
          }
        }];
      }));

      if (cancelled) return;
      const resolved = Object.fromEntries(entries.filter(([, value]) => Boolean(value)));
      exactFallbackCacheRef.current.set(fallbackCacheKey, resolved);
      setExactFallbackDetails(resolved);
    }

    resolveUnmappedStores().catch(() => {
      if (!cancelled) setExactFallbackDetails({});
    });

    return () => { cancelled = true; };
  }, [selectedStockId, activeSupplierProductName, exactGridStores, groups, session, similarSearchChars, sourceStoreId, renderedDashboard?.product_code]);

  const exactGridRows = useMemo(() => {
    const groupMap = new Map(groups.map((group) => [group.store.store_id, group]));
    return exactGridStores.map((store) => {
      const group = groupMap.get(store.store_id);
      const unresolved = group?.store?.store_match_status === 'unresolved';
      const fallback = exactFallbackDetails[store.store_id];
      if (unresolved && fallback?.product) {
        return {
          store,
          detail: fallback
        };
      }
      const productRow = {
        product_code: renderedDashboard?.product_code,
        product_name: unresolved
          ? 'No mapped product'
          : (group?.store?.product_name || match?.exact_match?.product_name || match?.supplier_stock?.supplier_product_name || '-'),
        sale_unit: group?.store?.sale_unit || group?.store?.unit_description || '-',
        stock: group?.store?.total_stock ?? 0,
        mrp: group?.store?.mrp,
        ptr: group?.store?.ptr
      };
      return {
        store,
        detail: {
          product: productRow,
          movement: group?.movement || [],
          batches: (group?.batches || []).map((row) => ({
            expiry_date: row.expirydate,
            stock: row.stock,
            mrp: row.mrp,
            batch_no: row.batchcode,
            grndate: row.grndate,
            lastsaledate: row.lastsaledate,
            last_purchase_date: row.grndate,
            last_sale_date: row.lastsaledate
          })),
          purchases: (group?.purchases || []).map((row) => ({
            qty: row.qty,
            free: row.free,
            overall_discount: row.overall_discount,
            date: row.grndate,
            grn_no: row.grn_no,
            supplier: row.supplier,
            discount: row.discount,
            mrp: row.mrp,
            ptr: row.ptr,
            cost: row.cost
          })),
          sales: (group?.sales || []).map((row) => ({
            qty: row.qty,
            date: row.bill_date,
            bill_no: row.bill_no,
            discount: row.discount,
            customer: row.customer_name,
            mrp: row.mrp
          }))
        }
      };
    });
  }, [renderedDashboard?.product_code, exactGridStores, exactFallbackDetails, groups, renderedMatch]);

  return (
    <section className="screen-panel supplier-analysis-workbench">
      <div className="supplier-toolbar">
        {tenants.length > 1 && (
          <label className="tenant-filter">
            Tenant
            <select
              value={tenantFilter}
              onChange={(event) => {
                // Switching tenant scope always forces a fresh warehouse choice:
                // in all-tenants mode the user must pick; scoped to one tenant the
                // effect above auto-selects that tenant's first warehouse.
                setWarehouseId('');
                setTenantFilter(event.target.value);
              }}
            >
              <option value="">All tenants</option>
              {tenants.map((tenant) => (
                <option key={tenant.tenant_id} value={tenant.tenant_id}>
                  {tenant.tenant_name || tenant.tenant_code}
                </option>
              ))}
            </select>
          </label>
        )}
        {(warehouses.length > 1 || (!tenantFilter && warehouses.length > 0)) && (
          <label className="tenant-filter">
            Warehouse
            <select value={selectedWarehouse?.store_id || ''} onChange={(event) => setWarehouseId(event.target.value)}>
              {!selectedWarehouse && <option value="">Select warehouse…</option>}
              {warehouses.map((w) => (
                <option key={w.store_id} value={w.store_id}>
                  {w.store_code}{!tenantFilter ? ` · ${tenantNameById.get(String(w.tenant_id)) || w.store_name || ''}` : ''}
                </option>
              ))}
            </select>
          </label>
        )}
        <button type="button" className="primary-button toolbar-import-btn" onClick={() => setImportOpen((open) => !open)}>
          {importOpen ? 'Close import' : 'Import Supplier Excel'}
        </button>
        <select
          className="toolbar-supplier-select"
          value={selectedSupplier}
          onChange={(event) => selectSupplier(event.target.value)}
        >
          <option value="">Choose supplier...</option>
          {suppliers.map((supplier) => (
            <option key={supplier.supplier_code} value={supplier.supplier_code}>
              {supplier.supplier_name || supplier.supplier_code}
            </option>
          ))}
        </select>
        <input
          className="toolbar-search"
          placeholder="Search supplier products..."
          value={productSearch}
          onChange={(event) => setProductSearch(event.target.value)}
          onKeyDown={handleProductSearchKeyDown}
          disabled={!selectedSupplier}
        />
        <select
          className="toolbar-supplier-select toolbar-mapping-filter"
          value={mappingFilter}
          onChange={(event) => setMappingFilter(event.target.value)}
          disabled={!selectedSupplier}
        >
          {SUPPLIER_MAPPING_FILTERS.map((filter) => (
            <option key={filter.value} value={filter.value}>{filter.label}</option>
          ))}
        </select>
        <label className="similar-search-slider" title="When no saved mapping is found, search stores using the first N characters of the product name.">
          <span>Fallback chars</span>
          <input
            type="range"
            min="3"
            max="12"
            step="1"
            value={similarSearchChars}
            onChange={handleSimilarSearchCharsChange}
          />
          <strong>{similarSearchChars}</strong>
        </label>
        <label className="stock-only-filter">
          <input type="checkbox" checked={onlyAvailable} onChange={(event) => setOnlyAvailable(event.target.checked)} />
          In stock only
        </label>
        <button type="button" className="secondary-button toolbar-import-btn" onClick={exportAnalysisReport} disabled={!selectedSupplier || reportBusy}>
          {reportBusy ? 'Building Report...' : 'Export Analysis Report'}
        </button>
        <MappingBadge products={products} />
      </div>

      {importOpen && (
        <SupplierExcelImport
          session={session}
          suppliers={suppliers}
          onImported={() => { setImportOpen(false); loadSuppliers(supplierSearch); if (selectedSupplier) loadProducts(selectedSupplier); }}
        />
      )}

      <div className="analysis-body">
        {showSupplierPanel && (
          <aside className="supplier-rail-compact">
            <input
              className="supplier-rail-search"
              placeholder="Search supplier..."
              value={supplierSearch}
              onChange={(event) => setSupplierSearch(event.target.value)}
            />
            <div className={`status-line ${supplierStatus.state}`}>{supplierStatus.message}</div>
            <div className="supplier-list-compact">
              {suppliers.map((supplier) => (
                <button
                  key={supplier.supplier_code}
                  type="button"
                  className={`supplier-row ${supplier.supplier_code === selectedSupplier ? 'selected' : ''}`}
                  onClick={() => selectSupplier(supplier.supplier_code)}
                >
                  <strong>{supplier.supplier_name || supplier.supplier_code}</strong>
                  <span>{supplier.available_count ?? 0}/{supplier.product_count ?? 0} in stock</span>
                </button>
              ))}
              {!suppliers.length && <div className="empty-state">No suppliers yet.</div>}
            </div>
          </aside>
        )}

        <div className={`product-list-panel-v2 ${!showSupplierPanel ? 'expanded' : ''}`}>
          {!showSupplierPanel && selectedSupplier && (
            <button type="button" className="change-supplier-btn" onClick={() => setShowSupplierPanel(true)}>
              &larr; Change Supplier
            </button>
          )}
          {selectedSupplier && <div className={`status-line ${productStatus.state}`}>{productStatus.message}</div>}
          {selectedSupplier && (
            <div className="procurement-grid-toolbar">
              <span className="procurement-grid-count">{visibleProducts.length} row(s)</span>
              <button type="button" className="secondary-button procurement-export-btn" onClick={exportOrderedRows}>
                Export Ordered Rows
              </button>
            </div>
          )}
          {selectedSupplier && exportStatus.message && <div className={`status-line ${exportStatus.state}`}>{exportStatus.message}</div>}
          {selectedSupplier && reportStatus.message && <div className={`status-line ${reportStatus.state}`}>{reportStatus.message}</div>}
          <div className="supplier-product-rows procurement-grid-scroll" ref={productListScrollRef}>
            {visibleProducts.length ? (
              <table className="procurement-grid">
                <thead>
                  <tr>
                    <th>Product</th>
                    <th className="num-col">Stock</th>
                    <th>Offer</th>
                    <th>Order Qty</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleProducts.map((row, index) => {
                    const dotState = row.has_mapping ? 'matched' : (rowMatchStates[row.supplier_stock_id] || 'unmatched');
                    const dotTitle = {
                      matched: 'Mapped (exact)',
                      similar: 'Similar matches found',
                      nomatch: 'No match found anywhere',
                      unmatched: 'Unmapped'
                    }[dotState];
                    const offer = offerBadge(row);
                    const qty = orderDrafts[row.supplier_stock_id] ?? '';
                    const edited = parseOrderQty(qty) > 0;
                    const isSelected = row.supplier_stock_id === selectedStockId;
                    return (
                      <tr
                        key={row.supplier_stock_id}
                        className={`${isSelected ? 'selected' : ''} ${edited ? 'edited' : ''}`}
                        onClick={() => selectProduct(row)}
                        onMouseEnter={() => prefetchAdjacentProducts(index)}
                        title={productTooltip(row)}
                      >
                        <td>
                          <div className="procurement-product-cell">
                            <span className={`match-dot ${dotState}`} title={dotTitle} />
                            <div className="procurement-product-text">
                              <strong>{row.supplier_product_name || 'Unnamed product'}</strong>
                              <span>{row.supplier_product_code || row.product_code || '-'}</span>
                            </div>
                          </div>
                        </td>
                        <td className="num-col">{formatQty(row.available_stock)}</td>
                        <td>
                          {offer ? (
                            <span className="procurement-offer-badge" title={offerTooltipLines(row).map(([label, value]) => `${label}: ${value}`).join('\n')}>
                              {offer}
                            </span>
                          ) : (
                            <span className="procurement-empty">-</span>
                          )}
                        </td>
                        <td>
                          <input
                            ref={(node) => { qtyRefs.current[row.supplier_stock_id] = node; }}
                            className="procurement-qty-input"
                            value={qty}
                            inputMode="text"
                            maxLength={8}
                            onFocus={() => { selectProduct(row); setActiveGridCell('qty'); }}
                            onChange={(event) => updateOrderQty(row.supplier_stock_id, event.target.value)}
                            onKeyDown={(event) => {
                              if (event.key === 'Enter') {
                                event.preventDefault();
                                moveGridSelection(row.supplier_stock_id, 1, 'qty');
                              } else if (event.key === 'ArrowDown') {
                                event.preventDefault();
                                moveGridSelection(row.supplier_stock_id, 1, 'qty');
                              } else if (event.key === 'ArrowUp') {
                                event.preventDefault();
                                moveGridSelection(row.supplier_stock_id, -1, 'qty');
                              }
                            }}
                          />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            ) : <div className="empty-state">
              {selectedSupplier
                ? filteredOutByStockOnly
                  ? `No ${mappingFilterLabel(mappingFilter).toLowerCase()} products are currently in stock. Turn off "In stock only" to view them.`
                  : 'No products for this supplier.'
                : 'Pick a supplier above to list its products.'}
            </div>}
          </div>
        </div>

        <div className="analysis-detail">
          {!selectedStockId && <div className="empty-state">Pick a procurement row to load offer, mapped product, stock, near expiry and purchase history.</div>}

          {selectedStockId && detailStatus.state !== 'ok' && (
            <div className={`status-line ${detailStatus.state}`}>{detailStatus.message}</div>
          )}

          {selectedStockId && (
            <div className={`status-line ${showingPersistedAnalysis ? 'loading' : 'ok'}`}>
              {showingPersistedAnalysis
                ? `Loading next product... Previous product kept visible.`
                : loadMetrics.selectionId === selectedStockId && loadMetrics.stockMs !== null
                  ? `Load time: stock ${Math.round(loadMetrics.stockMs)}ms`
                    + (loadMetrics.detailsMs !== null ? `, details ${Math.round(loadMetrics.detailsMs)}ms, total ${Math.round(loadMetrics.totalMs)}ms` : '')
                    + (loadMetrics.cached ? ' (cached)' : '')
                  : 'Timing capture pending...'}
            </div>
          )}

          {selectedStockId && match && !match.product_code && (
            <>
              <SimilarSearchHeader
                supplierProductName={activeSupplierProductName}
                similar={similar}
                selectedCandidate={selectedCandidate}
                onConfirm={() => confirmMapping(selectedCandidate.product.product_code)}
                confirmBusy={savingMapping}
              />
              <div className={`status-line ${similarStatus.state}`}>{similarStatus.message}</div>
              {similar && similar.byStore.size > 0 && (
                <div className="store-row-workspace no-side-search similar-store-workspace">
                  <section className="store-row-grid">
                    <StoreColumnHeaders hideSupplierColumn={hideSupplierColumn} sticky />
                    {similarGridStores.map((store) => {
                      const entry = similar.byStore.get(store.store_id);
                      const candidates = entry ? entry.candidates : [];
                      return (
                        <StoreDataRow
                          key={store.store_id || store.store_code}
                          store={store}
                          colorIndex={similarGridStores.indexOf(store)}
                          hasSearched
                          searchProducts={candidates}
                          detail={similarDetails[store.store_id]}
                          onProductSelect={(product) => selectSimilarCandidate(store.store_id, product)}
                          onSaleSelect={(s, row) => setBillDetail({ store: s, sale: row })}
                          onPurchaseSelect={undefined}
                          hideSupplierColumn={hideSupplierColumn}
                          visibility={visibility}
                          restrictWarehouse={false}
                          selected={selectedCandidate?.storeId === store.store_id}
                          onSelect={() => {}}
                        />
                      );
                    })}
                  </section>
                </div>
              )}
            </>
          )}

          {renderedDashboard && (
            <>
              <ProductInfoBar dashboard={renderedDashboard} match={renderedMatch} detailsLoading={!showingPersistedAnalysis && detailsStage === 'loading'} />
              <div className="store-row-workspace no-side-search exact-store-workspace">
                <section className="store-row-grid">
                  <StoreColumnHeaders hideSupplierColumn={hideSupplierColumn} sticky />
                  {exactGridRows.map(({ store, detail }, index) => (
                    <StoreDataRow
                      key={store.store_id || store.store_code}
                      store={store}
                      colorIndex={index}
                      hasSearched
                      searchProducts={[detail.product]}
                      detail={detail}
                      onProductSelect={() => {}}
                      onSaleSelect={(s, row) => setBillDetail({ store: s, sale: row })}
                      onPurchaseSelect={undefined}
                      hideSupplierColumn={hideSupplierColumn}
                      visibility={visibility}
                      restrictWarehouse={false}
                      selected={activeDetailStore === store.store_id}
                      onSelect={() => setActiveDetailStore(store.store_id)}
                    />
                  ))}
                </section>
              </div>
            </>
          )}
        </div>
      </div>
      {billDetail && (
        <BillDetailCard detail={billDetail} session={session} visibility={visibility} onClose={() => setBillDetail(null)} />
      )}
    </section>
  );
}

function MappingBadge({ products }) {
  const mapped = products.filter((row) => row.has_mapping).length;
  const unmapped = products.length - mapped;
  return (
    <div className="mapping-badge">
      <strong>{products.length}</strong> items
      <span className="mapping-badge-chip matched"><i />{mapped}</span>
      <span className="mapping-badge-chip unmatched"><i />{unmapped}</span>
    </div>
  );
}

// Result header for the Similar Search grid (Supplier Stock Analysis, no-exact-
// match path). "Use this match" stays disabled until a candidate is picked in
// any store's grid (see selectSimilarCandidate) - confirmMapping itself is
// untouched, this just supplies the productCode it expects.
function SimilarSearchHeader({ supplierProductName, similar, selectedCandidate, onConfirm, confirmBusy }) {
  return (
    <div className="similar-search-header">
      <div className="similar-search-field">
        <span>Supplier Product</span>
        <strong>{supplierProductName || '-'}</strong>
      </div>
      <div className="similar-search-field">
        <span>Search Mode</span>
        <strong>Similar Search</strong>
      </div>
      <div className="similar-search-field">
        <span>Search Key</span>
        <strong>{similar?.searchKey || '-'}</strong>
      </div>
      <div className="similar-search-field">
        <span>Matches Found</span>
        <strong>{similar?.matchesFound ?? 0} products</strong>
      </div>
      <div className="similar-search-field">
        <span>Stores</span>
        <strong>{similar?.storesWithMatches ?? 0}</strong>
      </div>
      <button
        type="button"
        className="primary-button similar-use-match-btn"
        disabled={!selectedCandidate || confirmBusy}
        onClick={onConfirm}
        title={selectedCandidate ? undefined : 'Click a candidate below first'}
      >
        {confirmBusy ? 'Saving...' : selectedCandidate ? `Use "${selectedCandidate.product.product_name}"` : 'Use this match'}
      </button>
    </div>
  );
}

// Single-line 40-48px replacement for the old KPI card strip + green "Matched
// to X" banner - the product is already highlighted in the left panel and
// Code/Name/Stock are already visible per-store in the grid below, so this
// bar only surfaces what isn't shown anywhere else at a glance.
function ProductInfoBar({ dashboard, match, detailsLoading }) {
  const rows = dashboard.all_store_stock || [];
  const resolvedRows = rows.filter((row) => row.store_match_status !== 'unresolved');
  const totalStock = rows.reduce((sum, row) => sum + Number(row.total_stock || 0), 0);
  const purchases = dashboard.purchases || [];
  const latestPurchase = purchases.reduce((latest, row) => (!latest || String(row.grndate) > String(latest.grndate) ? row : latest), null);
  const nearExpiryCount = (dashboard.batches || []).filter((row) => {
    const days = daysUntil(row.expirydate);
    return days !== null && days <= 60;
  }).length;
  const offer = offerBadge(match?.supplier_stock || {});
  const productName = resolvedRows.find((row) => row.product_name)?.product_name
    || match?.exact_match?.product_name
    || match?.supplier_stock?.supplier_product_name
    || '-';

  return (
    <div className="product-info-bar">
      <strong className="product-info-name">{productName}</strong>
      <span className="product-info-sep" />
      <span className="product-info-item">Code: {dashboard.product_code || '-'}</span>
      <span className="product-info-item">Mapped: {match?.exact_match?.product_name || productName}</span>
      <span className="product-info-item">Offer: {offer || '-'}</span>
      <span className="product-info-item">Matched Across {resolvedRows.length} Store{resolvedRows.length === 1 ? '' : 's'}</span>
      <span className="product-info-item">Stock: {totalStock}</span>
      <span className="product-info-item">Last Purchase: {detailsLoading ? '…' : formatDate(latestPurchase?.grndate)}</span>
      <span className="product-info-item">
        Near Expiry: {detailsLoading ? '…' : nearExpiryCount}
      </span>
    </div>
  );
}

function groupDashboardByStore(dashboard) {
  const stores = new Map();
  (dashboard.all_store_stock || []).forEach((row) => {
    stores.set(row.store_id, { store: row, batches: [], purchases: [], sales: [], movement: [] });
  });
  (dashboard.batches || []).forEach((row) => { stores.get(row.store_id)?.batches.push(row); });
  (dashboard.purchases || []).forEach((row) => { stores.get(row.store_id)?.purchases.push(row); });
  (dashboard.sales || []).forEach((row) => { stores.get(row.store_id)?.sales.push(row); });
  (dashboard.movement || []).forEach((row) => {
    stores.get(row.store_id)?.movement.push({
      period: row.month,
      pur: row.purchase_qty,
      tin: row.transfer_in_qty,
      sal: row.sale_qty,
      tout: row.transfer_out_qty,
      stk: row.stock
    });
  });
  return Array.from(stores.values());
}

function StoreOverviewCards({ groups, activeStoreId, onSelectStore }) {
  if (!groups.length) return null;
  return (
    <div className="store-overview-row">
      {groups.map((group, index) => {
        const store = group.store;
        const lastPurchase = group.purchases.reduce((latest, row) => (!latest || String(row.grndate) > String(latest.grndate) ? row : latest), null);
        const lastSale = group.sales.reduce((latest, row) => (!latest || String(row.bill_date) > String(latest.bill_date) ? row : latest), null);
        const expiryCount = group.batches.filter((row) => {
          const days = daysUntil(row.expirydate);
          return days !== null && days <= 60;
        }).length;
        return (
          <button
            type="button"
            key={store.store_id}
            className={`store-overview-card ${activeStoreId === store.store_id ? 'active' : ''}`}
            style={{ '--store-color': STORE_COLORS[index % STORE_COLORS.length] }}
            onClick={() => onSelectStore(store.store_id)}
          >
            <span className="store-overview-label">{storeLabel(store)}</span>
            <div className="store-overview-metric"><span>Stock</span><strong>{store.total_stock ?? 0}</strong></div>
            <div className="store-overview-metric"><span>MRP</span><strong>{store.mrp ?? '-'}</strong></div>
            <div className="store-overview-metric"><span>PTR</span><strong>{store.ptr ?? '-'}</strong></div>
            <div className="store-overview-metric"><span>Last Pur</span><strong>{formatDate(lastPurchase?.grndate)}</strong></div>
            <div className="store-overview-metric"><span>Last Sale</span><strong>{formatDate(lastSale?.bill_date)}</strong></div>
            <div className="store-overview-metric"><span>Expiry</span><strong className={expiryCount ? 'expiry-warn' : ''}>{expiryCount}</strong></div>
          </button>
        );
      })}
    </div>
  );
}

function StoreDetailPanel({ groups, activeStoreId, onSelectStore }) {
  if (!groups.length) return null;
  const active = groups.find((group) => group.store.store_id === activeStoreId) || groups[0];
  const activeIndex = groups.indexOf(active);
  return (
    <div className="store-detail-panel">
      <div className="store-tabs">
        {groups.map((group, index) => (
          <button
            type="button"
            key={group.store.store_id}
            className={`store-tab ${active.store.store_id === group.store.store_id ? 'active' : ''}`}
            style={{ '--store-color': STORE_COLORS[index % STORE_COLORS.length] }}
            onClick={() => onSelectStore(group.store.store_id)}
          >
            {storeLabel(group.store)}
          </button>
        ))}
      </div>
      <StoreDetailBody group={active} colorIndex={activeIndex} />
    </div>
  );
}

function StoreDetailBody({ group, colorIndex }) {
  const storeColor = STORE_COLORS[colorIndex % STORE_COLORS.length];
  const { store, batches, purchases, sales, movement } = group;
  const hasMovement = movement.length > 0;
  const hasBatches = batches.length > 0;
  const hasPurchases = purchases.length > 0;
  const hasSales = sales.length > 0;
  return (
    <div className="store-detail-body" style={{ '--store-color': storeColor }}>
      <div className="store-detail-top">
        <section className="detail-block stock-block">
          <h4>Stock</h4>
          <div className="store-product-grid-wrap">
            <GridRow
              cols={STOCK_COLS}
              tag="span"
              className="active-row"
              cells={[store.product_name || '-', store.sale_unit || store.unit_description || '-', store.total_stock ?? 0]}
            />
          </div>
        </section>
        <section className="detail-block trend-block">
          <h4>4-Month Trend</h4>
          {(hasMovement || purchases.length || sales.length)
            ? <MonthlyMovementChart rows={movement} purchases={purchases} sales={sales} />
            : <div className="detail-compact-placeholder">No chart data.</div>}
        </section>
      </div>
      <div className="store-detail-bottom">
        <section className={`detail-block ${hasBatches ? '' : 'detail-block--compact-empty'}`}>
          <h4>Batch</h4>
          {hasBatches ? (
            <RowDataCell
              className="batch-table"
              cols={BATCH_COLS}
              emptyMessage="No batch details."
              rows={batches.slice(0, 50).map((row) => [formatDate(row.expirydate), formatQty(row.stock), formatMoney(row.mrp), row.batchcode || '-'])}
            />
          ) : <div className="detail-compact-placeholder">No batch details.</div>}
        </section>
        <section className={`detail-block ${hasPurchases ? '' : 'detail-block--compact-empty'}`}>
          <h4>Purchase</h4>
          {hasPurchases ? (
            <RowDataCell
              className="purchase-table"
              cols={PURCHASE_COLS}
              emptyMessage="No purchase details."
              rows={purchases.slice(0, 50).map((row) => [
                formatQty(row.qty),
                formatQty(row.free ?? 0),
                formatMoney(row.overall_discount),
                formatMoney(row.discount),
                formatDate(row.grndate),
                row.grn_no || '-',
                row.supplier || '-'
              ])}
            />
          ) : <div className="detail-compact-placeholder">No purchase details.</div>}
        </section>
        <section className={`detail-block ${hasSales ? '' : 'detail-block--compact-empty'}`}>
          <h4>Billing</h4>
          {hasSales ? (
            <RowDataCell
              className="sales-table"
              cols={SALES_COLS}
              emptyMessage="No sales details."
              rows={sales.slice(0, 50).map((row) => [formatQty(row.qty), formatDate(row.bill_date), row.bill_no || '-', formatMoney(row.discount), row.customer_name || '-', formatMoney(row.mrp)])}
            />
          ) : <div className="detail-compact-placeholder">No billing details.</div>}
        </section>
      </div>
    </div>
  );
}

function SupplierExcelImport({ session, suppliers, onImported }) {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [mapping, setMapping] = useState({});
  const [supplierCode, setSupplierCode] = useState('');
  const [storeId, setStoreId] = useState('');
  const [status, setStatus] = useState({ state: 'idle', message: 'Choose an Excel file to preview.' });

  useEffect(() => { setStoreId(loadSettings().storeId || ''); }, []);

  async function handleFile(event) {
    const picked = event.target.files?.[0];
    if (!picked) return;
    setFile(picked);
    setStatus({ state: 'loading', message: 'Reading file...' });
    try {
      const result = await api.previewSupplierExcel(picked, session);
      setPreview(result);
      setMapping(result.suggested_mapping || {});
      setStatus({ state: 'ok', message: `${result.row_count} row(s) found in "${result.sheet_name}".` });
    } catch (error) {
      setPreview(null);
      setStatus({ state: 'error', message: error.message });
    }
  }

  async function runImport() {
    if (!file || !supplierCode) {
      setStatus({ state: 'error', message: 'Supplier code and a file are both required.' });
      return;
    }
    setStatus({ state: 'loading', message: 'Importing...' });
    try {
      const result = await api.importSupplierExcel({
        storeId,
        supplierCode,
        mapping,
        file,
        importedBy: session?.user?.username || session?.user?.name
      }, session);
      if (result.success === false) {
        setStatus({ state: 'error', message: `Missing mapping for: ${(result.missing || []).join(', ')}` });
        return;
      }
      setStatus({ state: 'ok', message: `Imported ${result.imported} row(s), resolved ${result.product_codes_resolved} against saved mappings.` });
      onImported();
    } catch (error) {
      setStatus({ state: 'error', message: error.message });
    }
  }

  return (
    <div className="table-wrap import-panel">
      <div className="form-grid">
        <label>
          Supplier code
          <input
            list="supplier-code-options"
            value={supplierCode}
            onChange={(event) => setSupplierCode(event.target.value)}
            placeholder="Enter or pick supplier code"
          />
          <datalist id="supplier-code-options">
            {suppliers.map((s) => <option key={s.supplier_code} value={s.supplier_code}>{s.supplier_name}</option>)}
          </datalist>
        </label>
        <label>
          Store ID
          <input value={storeId} onChange={(event) => setStoreId(event.target.value)} />
        </label>
        <label>
          Excel file
          <input type="file" accept=".xlsx,.xls" onChange={handleFile} />
        </label>
      </div>

      {preview && (
        <div className="mapping-grid">
          <div className="status-line idle">Match each column to a field. Required: {preview.targets.filter((t) => t.mandatory).map((t) => t.label).join(', ')}.</div>
          {preview.headers.map((header) => (
            <label key={header} className="mapping-row">
              {header}
              <select
                value={mapping[header] || ''}
                onChange={(event) => setMapping({ ...mapping, [header]: event.target.value })}
              >
                <option value="">Ignore</option>
                {preview.targets.map((target) => (
                  <option key={target.value} value={target.value}>{target.label}{target.mandatory ? ' *' : ''}</option>
                ))}
              </select>
            </label>
          ))}
        </div>
      )}

      <div className="action-row">
        <button className="primary-button" disabled={!file} onClick={runImport}>Import to supplier stock</button>
        <span className={`status ${status.state}`}>{status.message}</span>
      </div>
    </div>
  );
}

function ScreenHeader({ title, subtitle }) {
  return (
    <header className="screen-header">
      <div>
        <h2>{title}</h2>
        <p>{subtitle}</p>
      </div>
    </header>
  );
}

function DataTable({ columns, rows, status, emptyMessage = 'No data to show yet.', className = '' }) {
  return (
    <div className={`table-wrap ${className}`}>
      <div className={`status-line ${status.state}`}>{status.message}</div>
      {rows.length ? (
        <table>
          <thead>
            <tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`${row[0]}-${index}`}>{row.map((cell, cellIndex) => <td key={cellIndex}>{cell}</td>)}</tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div className="empty-state">{emptyMessage}</div>
      )}
    </div>
  );
}




































