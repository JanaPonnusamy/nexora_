import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from './api/client.js';
import {
  clearSession,
  loadSession,
  loadSettings,
  saveSession,
  saveSettings
} from './state/session.js';

const screens = [
  { id: 'stock', label: 'Stock Availability', module: 'stock_availability' },
  { id: 'analysis', label: 'Supplier Stock Analysis', module: 'supplier_stock_analysis' },
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

function isSuperAdmin(session) {
  const roles = session?.user?.roles || [];
  const roleNames = roles.map((role) => String(role?.role_name || role?.role || '').toLowerCase());
  return roleNames.some((name) => name.includes('super admin') || name.includes('superadmin'));
}

function isWarehouseStore(store) {
  return String(store?.store_code || '').trim().toUpperCase() === 'NMW';
}

export default function App() {
  const [settings, setSettings] = useState(loadSettings);
  const [session, setSession] = useState(loadSession);
  const [activeScreen, setActiveScreen] = useState('stock');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(true);

  const isConfigured = Boolean(settings.tenantId && settings.storeId);

  const navItems = useMemo(() => {
    const modules = userModules(session?.user);
    if (!modules.length) return screens;
    return screens.filter((screen) => screen.id === 'settings' || modules.includes(screen.module) || modules.includes(screen.id));
  }, [session]);

  useEffect(() => {
    if (!isConfigured) {
      setActiveScreen('settings');
      return;
    }
    if (!navItems.some((item) => item.id === activeScreen)) {
      setActiveScreen(navItems[0]?.id || 'settings');
    }
  }, [activeScreen, navItems, isConfigured]);

  useEffect(() => {
    const storeName = session?.user?.roles?.[0]?.store_name || settings.storeName;
    document.title = storeName ? `Nexora Supplier Stock · ${storeName}` : 'Nexora Supplier Stock';
  }, [session, settings.storeName]);

  function persistSettings(next) {
    setSettings(saveSettings(next));
  }

  function handleLogin(loginPayload) {
    setSession(saveSession(loginPayload));
  }

  function handleLogout() {
    clearSession();
    setSession(null);
  }

  return (
    <div className={`app-shell ${sidebarCollapsed ? 'sidebar-collapsed' : ''}`}>
      <aside className="sidebar">
        <button
          className="collapse-button"
          onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
          title={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {sidebarCollapsed ? '>' : '<'}
        </button>
        <div className="brand-block">
          <div className="brand-mark">N</div>
          <div>
            <h1>Nexora</h1>
            <p>Supplier Stock Client</p>
          </div>
        </div>

        {session ? (
          <div className="user-panel">
            <span>{session.user?.name || session.user?.username || 'Signed in user'}</span>
            <strong>{session.user?.roles?.[0]?.role_name || session.user?.role || session.user?.roleName || 'Role pending'}</strong>
          </div>
        ) : (
          <div className="user-panel muted">Sign in to unlock modules</div>
        )}

        <nav className="nav-list">
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

        {session && (
          <button className="ghost-button" onClick={handleLogout}>Sign out</button>
        )}
      </aside>

      <DevViewportSwitcher />

      <main className="workspace">
        {!isConfigured ? (
          <SettingsScreen settings={settings} onSave={persistSettings} requireAdminGate />
        ) : !session && activeScreen !== 'settings' ? (
          <LoginScreen onLogin={handleLogin} onOpenSettings={() => setActiveScreen('settings')} />
        ) : activeScreen === 'settings' ? (
          <SettingsScreen settings={settings} onSave={persistSettings} />
        ) : activeScreen === 'analysis' ? (
          <SupplierStockAnalysis session={session} />
        ) : (
          <StockAvailability session={session} settings={settings} onOpenSettings={() => setActiveScreen('settings')} />
        )}
      </main>
    </div>
  );
}

const VIEWPORT_PRESETS = [
  { label: 'Window size', width: 0, height: 0 },
  { label: '1366 x 768', width: 1366, height: 768 },
  { label: '1440 x 900', width: 1440, height: 900 },
  { label: '1600 x 900', width: 1600, height: 900 },
  { label: '1920 x 1080', width: 1920, height: 1080 }
];

function DevViewportSwitcher() {
  const [isDev, setIsDev] = useState(false);
  const [selected, setSelected] = useState('');

  useEffect(() => {
    if (!window.nexoraDesktop?.isDev) return;
    window.nexoraDesktop.isDev().then(setIsDev).catch(() => setIsDev(false));
  }, []);

  if (!isDev || !window.nexoraDesktop) return null;

  function handleChange(event) {
    const value = event.target.value;
    setSelected(value);
    if (!value) {
      window.nexoraDesktop.maximizeViewport();
      return;
    }
    const preset = VIEWPORT_PRESETS.find((item) => `${item.width}x${item.height}` === value);
    if (preset) window.nexoraDesktop.setViewport(preset.width, preset.height);
  }

  return (
    <div className="dev-viewport-switcher">
      <span>Dev viewport</span>
      <select value={selected} onChange={handleChange}>
        {VIEWPORT_PRESETS.map((preset) => (
          <option key={preset.label} value={preset.width ? `${preset.width}x${preset.height}` : ''}>
            {preset.label}
          </option>
        ))}
      </select>
    </div>
  );
}

function SettingsScreen({ settings, onSave, requireAdminGate = false }) {
  const [draft, setDraft] = useState(settings);
  const [status, setStatus] = useState({ state: 'idle', message: '' });
  const [tenants, setTenants] = useState([]);
  const [stores, setStores] = useState([]);
  const [devices, setDevices] = useState([]);
  const [adminUnlocked, setAdminUnlocked] = useState(!requireAdminGate);
  const [adminForm, setAdminForm] = useState({ username: '', password: '' });
  const [adminStatus, setAdminStatus] = useState({ state: 'idle', message: '' });

  useEffect(() => setDraft(settings), [settings]);

  async function unlockAdmin(event) {
    event.preventDefault();
    setAdminStatus({ state: 'loading', message: 'Checking admin credentials...' });
    try {
      const response = await api.login(adminForm);
      const user = response.user || response.data?.user || response;
      const roleNames = (user?.roles || []).map((role) => String(role?.role_name || role?.role || '').toLowerCase());
      if (!roleNames.some((name) => name.includes('admin'))) {
        setAdminStatus({ state: 'error', message: 'This account does not have admin access.' });
        return;
      }
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
      const [tenantRows, storeRows] = await Promise.all([api.listTenants(), api.listStores()]);
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
      });
      setStatus({ state: 'ok', message: `Activation requested. Client ID: ${result.client_id} (${result.status})` });
      setDraft({ ...draft, clientId: result.client_id });
    } catch (error) {
      setStatus({ state: 'error', message: error.message });
    }
  }

  async function loadDevices() {
    setStatus({ state: 'loading', message: 'Loading desktop devices...' });
    try {
      const result = await api.listDesktopDevices();
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
      });
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

function StockAvailability({ session, settings, onOpenSettings }) {
  const [query, setQuery] = useState('');
  const [onlyStock, setOnlyStock] = useState(false);
  const [allStores, setAllStores] = useState([]);
  const [searchStores, setSearchStores] = useState([]);
  const [storeDetails, setStoreDetails] = useState({});
  const [selectedStoreId, setSelectedStoreId] = useState(session?.user?.roles?.[0]?.store_id || '');
  const [hasSearched, setHasSearched] = useState(false);
  const [status, setStatus] = useState({ state: 'idle', message: 'Type product name to search.' });
  const [purchaseDetail, setPurchaseDetail] = useState(null);
  const [nonMovingProducts, setNonMovingProducts] = useState([]);
  const [nonMovingLoading, setNonMovingLoading] = useState(true);
  const [nonMovingIndex, setNonMovingIndex] = useState(0);
  const [isAutoQuery, setIsAutoQuery] = useState(false);
  const searchInputRef = useRef(null);

  const loginStoreId = session?.user?.roles?.[0]?.store_id || loadSettings().storeId;
  const canViewPurchase = canViewPurchaseDetails(session);
  const hideSupplierColumn = isSalesmanOnly(session);
  const searchIdRef = useRef(0);
  // In-memory caches: instant re-render for anything already fetched this session.
  // searchCacheRef: normalized query -> stores[] from the search API.
  // detailCacheRef: "storeId:productCode" -> fully loaded store detail (incl. bill items).
  const searchCacheRef = useRef(new Map());
  const detailCacheRef = useRef(new Map());

  useEffect(() => {
    api.listStores().then((rows) => setAllStores(asArray(rows))).catch(() => setAllStores([]));
  }, []);

  useEffect(() => {
    if (!allStores.length) return;
    Promise.all(allStores.map((store) => api.getNonMovingStock(store.store_id, session, { dwellDays: 120, minPurAge: 10, limit: 50 })
      .then((result) => asArray(result?.rows)
        .map((row) => ({ ...row, __storeName: store.store_name || store.store_code })))
      .catch(() => [])))
      .then((lists) => {
        const merged = lists.flat();
        merged.sort((a, b) => {
          const valueA = Number(a.TotalStock ?? 0) * Number(a.MRP ?? 0);
          const valueB = Number(b.TotalStock ?? 0) * Number(b.MRP ?? 0);
          return valueB - valueA;
        });
        setNonMovingProducts(merged);
        setNonMovingLoading(false);
      });
  }, [allStores]);

  useEffect(() => {
    if (nonMovingProducts.length < 2) return;
    const timer = setInterval(() => {
      setNonMovingIndex((index) => (index + 1) % nonMovingProducts.length);
    }, 6000);
    return () => clearInterval(timer);
  }, [nonMovingProducts]);

  function nonMovingStep(delta) {
    if (!nonMovingProducts.length) return;
    setNonMovingIndex((index) => (index + delta + nonMovingProducts.length) % nonMovingProducts.length);
  }

  useEffect(() => {
    if (hasSearched || query.trim() || !nonMovingProducts.length) return;
    const productName = nonMovingProducts[0]?.ProductName;
    if (productName) {
      setQuery(productName);
      setIsAutoQuery(true);
    }
  }, [nonMovingProducts, hasSearched, query]);

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
    const result = await api.getStockCore(storeId, product.product_code, session, { months: 3 });
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

  async function fetchBillItems(storeId, core) {
    const firstSale = core.sales[0];
    if (!firstSale?.bill_no) return [];
    return asArray(await api.getBillItems(storeId, firstSale.bill_no, firstSale.date, session).catch(() => []));
  }

  function attachBillItemsAsync(searchId, storeId, core) {
    if (core.billItems.length || !core.sales[0]?.bill_no) return; // already have it (from cache) or nothing to fetch
    const firstSale = core.sales[0];
    fetchBillItems(storeId, core).then((billItems) => {
      const cacheKey = `${storeId}:${core.product.product_code}`;
      const cached = detailCacheRef.current.get(cacheKey);
      if (cached) { cached.billItems = billItems; cached.activeBillNo = firstSale.bill_no; } // keep cache entry in sync
      if (searchIdRef.current !== searchId) return;
      setStoreDetails((prev) => (prev[storeId]
        ? { ...prev, [storeId]: { ...prev[storeId], billItems, activeBillNo: firstSale.bill_no } }
        : prev));
    });
  }

  function selectSale(storeId, sale) {
    if (!sale?.bill_no) return;
    setStoreDetails((prev) => (prev[storeId] ? { ...prev, [storeId]: { ...prev[storeId], activeBillNo: sale.bill_no } } : prev));
    api.getBillItems(storeId, sale.bill_no, sale.date, session)
      .then((billItems) => {
        const items = asArray(billItems);
        setStoreDetails((prev) => (prev[storeId] && prev[storeId].activeBillNo === sale.bill_no
          ? { ...prev, [storeId]: { ...prev[storeId], billItems: items } }
          : prev));
      })
      .catch(() => {});
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
      Object.entries(seeded).forEach(([storeId, core]) => attachBillItemsAsync(searchId, storeId, core));

      if (!toFetch.length) {
        const elapsedMs = Math.round(performance.now() - startedAt);
        setStatus({ state: 'ok', message: `${total} product match(es) found. All stores loaded in ${elapsedMs}ms (cached).` });
        return;
      }

      setStatus({ state: 'loading', message: `${total} product match(es) found. Loading ${toFetch.length} store(s)...` });

      // Independent processor per store: each one fetches and renders as soon
      // as it's ready, instead of the whole grid waiting on the slowest store.
      // Every callback re-checks searchIdRef so results from a search the user
      // has already replaced (by typing again) never overwrite newer state.
      let settled = 0;
      toFetch.forEach((store) => {
        const product = store.products[0];
        loadStoreCore(store.store_id, product)
          .then((core) => {
            if (searchIdRef.current !== searchId) return;
            setStoreDetails((prev) => ({ ...prev, [store.store_id]: core }));
            attachBillItemsAsync(searchId, store.store_id, core);
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
        attachBillItemsAsync(searchId, storeId, core);
      })
      .catch(() => {});
  }

  const searchProductsByStore = new Map(searchStores.map((store) => [store.store_id, store.products || []]));
  const visibleStores = allStores.length ? allStores : Array.from({ length: 5 }, (_, index) => ({ store_id: 'pending-' + index, store_name: 'Loading store...' }));
  const stores = orderStores(visibleStores, loginStoreId, settings?.storeOrder || []);

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
        <div className={`status-line ${status.state}`}>{status.message}</div>
        <MovementLegend />
        <div className="current-store-badge">
          <span>This device: {session?.user?.roles?.[0]?.store_name || settings?.storeName || 'Not registered'}</span>
          <button type="button" className="link-button" onClick={onOpenSettings}>Store order settings</button>
        </div>
      </div>

      <NonMovingHighlightCard
        nonMovingProducts={nonMovingProducts}
        nonMovingLoading={nonMovingLoading}
        nonMovingIndex={nonMovingIndex}
        onPrev={() => nonMovingStep(-1)}
        onNext={() => nonMovingStep(1)}
        onSearch={(productName) => {
          if (!productName) return;
          setIsAutoQuery(false);
          setQuery(productName);
        }}
      />

      <div className="store-row-workspace no-side-search">
        <section className="store-row-grid">
          {stores.map((store, index) => (
            <StoreDataRow
              key={store.store_id || store.store_code}
              store={store}
              colorIndex={index}
              hasSearched={hasSearched}
              searchProducts={searchProductsByStore.get(store.store_id) || []}
              detail={storeDetails[store.store_id]}
              onProductSelect={(product) => handleProductSelect(store.store_id, product)}
              onSaleSelect={selectSale}
              onPurchaseSelect={canViewPurchase ? (row) => setPurchaseDetail({ store, row }) : undefined}
              hideSupplierColumn={hideSupplierColumn}
              restrictWarehouse={isWarehouseStore(store) && !isSuperAdmin(session)}
              selected={selectedStoreId === store.store_id}
              onSelect={() => setSelectedStoreId(store.store_id)}
            />
          ))}
        </section>
      </div>

      {purchaseDetail && (
        <PurchaseDetailCard detail={purchaseDetail} onClose={() => setPurchaseDetail(null)} />
      )}
    </section>
  );
}

const STORE_COLORS = ['#2563eb', '#15803d', '#b45309', '#7c3aed', '#be123c', '#0d9488'];

const STOCK_COLS = '1fr 46px 55px';
const BATCH_COLS = '68px 46px 58px 78px';
const PURCHASE_COLS = '40px 38px 70px 58px 1fr';
const PURCHASE_COLS_NO_SUPPLIER = '40px 38px 70px 1fr';
const SALES_COLS = '36px 62px 80px 42px 1fr 52px';
const BILL_COLS = '1fr 36px 42px 52px 52px 62px';

function StoreColumnHeaders({ hideSupplierColumn = false, restrictWarehouse = false }) {
  const purchaseCols = hideSupplierColumn ? PURCHASE_COLS_NO_SUPPLIER : PURCHASE_COLS;
  const purchaseHeaders = hideSupplierColumn ? ['Qty', 'Free', 'GRN Date', 'GRN No'] : ['Qty', 'Free', 'GRN Date', 'GRN No', 'Supplier'];

  if (restrictWarehouse) {
    return (
      <div className="store-column-headers">
        <span className="store-header-cell" />
        <div className="header-cell warehouse-only-header-cell">
          <div className="header-cell-title">Stock</div>
          <GridRow cols={STOCK_COLS} cells={['Product', 'Unit', 'Stock']} tag="span" />
        </div>
      </div>
    );
  }

  return (
    <div className="store-column-headers">
      <span className="store-header-cell" />
      <div className="header-cell">
        <div className="header-cell-title">Stock</div>
        <GridRow cols={STOCK_COLS} cells={['Product', 'Unit', 'Stock']} tag="span" />
      </div>
      <div className="header-cell">
        <div className="header-cell-title">3-Month Trend</div>
      </div>
      <div className="header-cell">
        <div className="header-cell-title">Batch</div>
        <GridRow cols={BATCH_COLS} cells={['Exp', 'Stk', 'MRP', 'Batch No']} tag="span" />
      </div>
      <div className="header-cell">
        <div className="header-cell-title">Purchase</div>
        <GridRow cols={purchaseCols} cells={purchaseHeaders} tag="span" />
      </div>
      <div className="header-cell">
        <div className="header-cell-title">Sales</div>
        <GridRow cols={SALES_COLS} cells={['Qty', 'Date', 'Bill No', 'Dis%', 'Customer', 'MRP']} tag="span" />
      </div>
      <div className="header-cell">
        <div className="header-cell-title">Billing</div>
        <GridRow cols={BILL_COLS} cells={['Product', 'Qty', 'Dis%', 'MRP', 'Packing', 'Amount']} tag="span" />
      </div>
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

function StoreDataRow({ store, colorIndex, hasSearched, searchProducts, detail, onProductSelect, onSaleSelect, onPurchaseSelect, hideSupplierColumn, restrictWarehouse, selected, onSelect }) {
  const batches = detail?.batches || [];
  const purchases = detail?.purchases || [];
  const sales = detail?.sales || [];
  const movement = detail?.movement || [];
  const billItems = detail?.billItems || [];
  const activeBillNo = detail?.activeBillNo || sales[0]?.bill_no || null;
  const salesman = billItems[0]?.salesman;
  const billTotal = billItems.reduce((sum, row) => sum + (Number(row.amount) || 0), 0);
  const storeColor = STORE_COLORS[colorIndex % STORE_COLORS.length];
  const currentProduct = detail?.product?.product_name;
  const pending = hasSearched && searchProducts.length > 0 && detail === undefined;

  return (
    <article
      className={`store-data-row ${selected ? 'selected' : ''} ${pending ? 'pending' : ''}`}
      style={{ '--store-color': storeColor }}
    >
      <div className="store-row-header-bar" onClick={onSelect}>
        <span className="store-row-header-name">{store.store_name || 'Loading store...'}</span>
        <span className="store-row-header-product">
          {restrictWarehouse ? 'Stock search: ' : ''}
          {currentProduct ? `${restrictWarehouse ? '' : 'Showing: '}${currentProduct}` : pending ? 'Loading...' : hasSearched ? 'No product selected' : 'Waiting for search...'}
        </span>
      </div>

      <StoreColumnHeaders
        hideSupplierColumn={hideSupplierColumn}
        restrictWarehouse={restrictWarehouse}
      />

      <div className="store-row-grid-body" onClick={onSelect}>
        <div className="store-row-label">
          {(store.store_code || shortStoreName(store.store_name)).split('').map((char, index) => (
            <strong key={index}>{char}</strong>
          ))}
        </div>

        <section className={`row-cell stock-cell ${restrictWarehouse ? 'stock-cell-full' : ''}`}>
          <StoreProductGrid
            products={searchProducts}
            hasSearched={hasSearched}
            selectedProductCode={detail?.product?.product_code}
            onProductSelect={onProductSelect}
          />
        </section>

        {restrictWarehouse ? null : (
          <>
            <section className="row-cell trend-cell">
              {pending ? <SkeletonBlock lines={1} /> : <MonthlyMovementChart rows={movement} />}
            </section>

            <RowDataCell
              className="batch-table"
              cols={BATCH_COLS}
              emptyMessage="No batch details."
              pending={pending}
              rows={batches.slice(0, 20).map((row) => [formatDate(row.expiry_date), row.stock ?? '-', row.mrp ?? '-', row.batch_no || '-'])}
            />

            <RowDataCell
              className={`purchase-table ${onPurchaseSelect ? 'clickable' : ''}`}
              cols={hideSupplierColumn ? PURCHASE_COLS_NO_SUPPLIER : PURCHASE_COLS}
              emptyMessage="No purchase details."
              pending={pending}
              rows={purchases.slice(0, 20).map((row) => (hideSupplierColumn
                ? [row.qty ?? '-', row.free ?? 0, formatDate(row.date), row.grn_no || '-']
                : [row.qty ?? '-', row.free ?? 0, formatDate(row.date), row.grn_no || '-', row.supplier || '-']))}
              onRowClick={onPurchaseSelect ? (index) => onPurchaseSelect(purchases[index]) : undefined}
            />

            <section className="row-cell row-data-cell sales-table">
              {pending ? (
                <SkeletonBlock lines={4} />
              ) : sales.length ? (
                <div className="row-table-wrap">
                  {sales.slice(0, 20).map((row, index) => (
                    <GridRow
                      key={index}
                      cols={SALES_COLS}
                      tag="span"
                      className={row.bill_no && row.bill_no === activeBillNo ? 'active-row' : ''}
                      cells={[row.qty ?? '-', formatDate(row.date), row.bill_no || '-', row.discount ?? 0, row.customer || '-', row.mrp ?? '-']}
                      onClick={() => onSaleSelect(store.store_id, row)}
                    />
                  ))}
                </div>
              ) : (
                <div className="row-empty-state">No sales details.</div>
              )}
            </section>

            <section className="row-cell row-data-cell bill-table">
              {pending ? (
                <SkeletonBlock lines={4} />
              ) : (
                <>
                  {activeBillNo && (
                    <div className="bill-meta">
                      Bill {activeBillNo}{salesman ? ` · Rep: ${salesman}` : ''}
                      {billItems.length ? ` · Total: ${billTotal.toFixed(2)}` : ''}
                    </div>
                  )}
                  {billItems.length ? (
                    <div className="row-table-wrap">
                      {billItems.slice(0, 20).map((row, index) => (
                        <GridRow
                          key={index}
                          cols={BILL_COLS}
                          tag="span"
                          cells={[row.product_name || '-', row.qty ?? '-', row.discount_pct ?? 0, row.mrp ?? '-', row.sale_unit || '-', row.amount ?? '-']}
                        />
                      ))}
                    </div>
                  ) : (
                    <div className="row-empty-state">No bill details.</div>
                  )}
                </>
              )}
            </section>
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

function PurchaseDetailCard({ detail, onClose }) {
  const { store, row } = detail;
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="purchase-detail-card" onClick={(event) => event.stopPropagation()}>
        <div className="purchase-detail-header">
          <strong>Purchase Details · {store.store_name || store.store_code}</strong>
          <button type="button" className="ghost-button" onClick={onClose}>Close</button>
        </div>
        <div className="purchase-detail-grid">
          {PURCHASE_DETAIL_FIELDS.filter(([key]) => row[key] !== undefined && row[key] !== null && row[key] !== '').map(([key, label]) => (
            <div className="purchase-detail-item" key={key}>
              <span>{label}</span>
              <strong>{key === 'date' ? formatDate(row[key]) : row[key]}</strong>
            </div>
          ))}
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

function SkeletonBlock({ lines = 3 }) {
  return (
    <div className="skeleton-block">
      {Array.from({ length: lines }, (_, index) => <span key={index} className="skeleton-line" />)}
    </div>
  );
}

function StoreProductGrid({ products, hasSearched, selectedProductCode, onProductSelect }) {
  if (!products.length) {
    return <div className={hasSearched ? 'not-found-card' : 'waiting-card'}>{hasSearched ? 'No matching products.' : 'Waiting.'}</div>;
  }

  return (
    <div className="store-product-grid-wrap">
      {products.slice(0, 20).map((product, index) => (
        <GridRow
          key={`${product.product_code || product.product_name}-${index}`}
          cols={STOCK_COLS}
          tag="span"
          className={product.product_code === selectedProductCode ? 'active-row' : ''}
          cells={[product.product_name || '-', product.sale_unit || product.unitdescription || '-', product.stock ?? 0]}
          onClick={() => onProductSelect(product)}
        />
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

function MonthlyMovementChart({ rows }) {
  const months = rows.slice(-3);
  if (!months.length) return <div className="empty-state">No chart data yet.</div>;

  const maxValue = Math.max(1, ...months.flatMap((row) => [
    Number(row.pur || 0) + Number(row.tin || 0),
    Number(row.sal || 0) + Number(row.tout || 0),
    Number(row.stk || 0)
  ]));

  return (
    <div className="movement-chart">
      {months.map((row) => {
        const pur = Number(row.pur || 0);
        const tin = Number(row.tin || 0);
        const sal = Number(row.sal || 0);
        const tout = Number(row.tout || 0);
        const stock = Number(row.stk || 0);
        return (
          <div className="movement-month" key={row.period}>
            <div className="movement-bars">
              <MovementBar segments={[{ value: pur, cls: 'pur' }, { value: tin, cls: 'tin' }]} max={maxValue} />
              <MovementBar segments={[{ value: sal, cls: 'sale' }, { value: tout, cls: 'tout' }]} max={maxValue} />
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

function NonMovingHighlightCard({ nonMovingProducts, nonMovingLoading, nonMovingIndex, onPrev, onNext, onSearch }) {
  if (!nonMovingProducts?.length) {
    return (
      <section className="non-moving-global-card">
        <div className="row-empty-state">
          {nonMovingLoading ? 'Loading non-moving stock…' : 'No non-moving stock found.'}
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

function NonMovingDetailPanel({ product, onSearch, nav }) {
  const stock = Number(product.TotalStock ?? product.Batch_Stock ?? 0);
  const mrp = Number(product.MRP ?? 0);
  const totalValue = stock * mrp;
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
        <div><span>Stock Value</span><strong className="non-moving-value-highlight">{totalValue ? totalValue.toFixed(2) : '-'}</strong></div>
        <div className={expired ? 'expiry-dead' : nearExpiry ? 'expiry-highlight' : ''}>
          <span>Expiry</span>
          <strong>
            {formatDate(product.ExpiryDate)}
            {expiryNote && <em className="non-moving-expiry-note">{expiryNote}</em>}
          </strong>
        </div>
        <div><span>Stock Qty</span><strong>{stock}</strong></div>
        <div><span>PTR (Cost)</span><strong>{product.PurchasePrice ?? '-'}</strong></div>
        <div><span>MRP</span><strong>{mrp || '-'}</strong></div>
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
function SupplierStockAnalysis({ session }) {
  const [suppliers, setSuppliers] = useState([]);
  const [supplierSearch, setSupplierSearch] = useState('');
  const [supplierStatus, setSupplierStatus] = useState({ state: 'idle', message: 'Loading suppliers...' });
  const [selectedSupplier, setSelectedSupplier] = useState('');

  const [products, setProducts] = useState([]);
  const [productSearch, setProductSearch] = useState('');
  const [onlyAvailable, setOnlyAvailable] = useState(true);
  const [productStatus, setProductStatus] = useState({ state: 'idle', message: 'Select a supplier to list products.' });

  const [selectedStockId, setSelectedStockId] = useState('');
  const [match, setMatch] = useState(null);
  const [dashboard, setDashboard] = useState(null);
  const [detailStatus, setDetailStatus] = useState({ state: 'idle', message: 'Select a product to analyze.' });

  const [importOpen, setImportOpen] = useState(false);
  const selectedStockIdRef = useRef('');
  useEffect(() => { selectedStockIdRef.current = selectedStockId; }, [selectedStockId]);

  useEffect(() => { loadSuppliers(''); }, []);

  useEffect(() => {
    const timer = setTimeout(() => loadSuppliers(supplierSearch), 200);
    return () => clearTimeout(timer);
  }, [supplierSearch]);

  useEffect(() => {
    if (!selectedSupplier) { setProducts([]); return; }
    const timer = setTimeout(() => loadProducts(), 200);
    return () => clearTimeout(timer);
  }, [selectedSupplier, productSearch, onlyAvailable]);

  async function loadSuppliers(search) {
    setSupplierStatus({ state: 'loading', message: 'Loading suppliers...' });
    try {
      const response = await api.getSuppliers(session, { search });
      const items = asArray(response);
      setSuppliers(items);
      setSupplierStatus({ state: 'ok', message: items.length ? `${items.length} supplier(s).` : 'No suppliers found. Import an Excel sheet to begin.' });
    } catch (error) {
      setSuppliers([]);
      setSupplierStatus({ state: 'error', message: error.message });
    }
  }

  async function loadProducts() {
    setProductStatus({ state: 'loading', message: 'Loading supplier products...' });
    try {
      const response = await api.getSupplierProducts(selectedSupplier, session, { search: productSearch, onlyAvailable: onlyAvailable ? 1 : 0 });
      const items = asArray(response);
      setProducts(items);
      setProductStatus({ state: 'ok', message: `${items.length} items` });
    } catch (error) {
      setProducts([]);
      setProductStatus({ state: 'error', message: error.message });
    }
  }

  function selectSupplier(code) {
    setSelectedSupplier(code);
    setSelectedStockId('');
    setMatch(null);
    setDashboard(null);
  }

  async function selectProduct(row) {
    const stockId = row.supplier_stock_id;
    setSelectedStockId(stockId);
    setMatch(null);
    setDashboard(null);
    setDetailStatus({ state: 'loading', message: 'Loading match and stock details...' });
    try {
      // Single round trip: the dashboard endpoint resolves the match internally
      // (exact code -> mapping -> suggestions) and only builds the dashboard when resolved.
      const result = await api.getSupplierDashboard(stockId, session);
      if (selectedStockIdRef.current !== stockId) return;
      setMatch(result);
      if (result.product_code) {
        setDashboard(result.dashboard || null);
        setDetailStatus({ state: 'ok', message: result.match_status === 'exact' ? 'Exact mapping found.' : 'Resolved from a saved mapping.' });
      } else {
        setDetailStatus({ state: 'ok', message: result.suggestions?.length ? `No exact match. ${result.suggestions.length} suggestion(s) found - pick the right product.` : 'No exact or suggested match found.' });
      }
    } catch (error) {
      if (selectedStockIdRef.current !== stockId) return;
      setDetailStatus({ state: 'error', message: error.message });
    }
  }

  async function confirmMapping(productCode) {
    if (!match?.supplier_stock) return;
    const row = match.supplier_stock;
    setDetailStatus({ state: 'loading', message: 'Saving mapping...' });
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
      await selectProduct({ supplier_stock_id: selectedStockId });
      loadProducts();
    } catch (error) {
      setDetailStatus({ state: 'error', message: error.message });
    }
  }

  return (
    <section className="screen-panel supplier-analysis-workbench">
      <ScreenHeader
        title="Supplier Stock Analysis"
        subtitle="Import a supplier stock sheet, resolve it against the product catalogue, then review live stock across every store."
      />
      <div className="action-row">
        <button className="primary-button" onClick={() => setImportOpen((open) => !open)}>
          {importOpen ? 'Close import' : 'Import supplier Excel'}
        </button>
      </div>

      {importOpen && (
        <SupplierExcelImport
          session={session}
          suppliers={suppliers}
          onImported={() => { setImportOpen(false); loadSuppliers(supplierSearch); if (selectedSupplier) loadProducts(); }}
        />
      )}

      <div className={`analysis-layout ${selectedSupplier ? 'supplier-collapsed' : ''}`}>
        {!selectedSupplier && (
          <aside className="supplier-rail">
            <input
              placeholder="Search supplier..."
              value={supplierSearch}
              onChange={(event) => setSupplierSearch(event.target.value)}
            />
            <div className={`status-line ${supplierStatus.state}`}>{supplierStatus.message}</div>
            <div className="supplier-list">
              {suppliers.map((supplier) => (
                <button
                  key={supplier.supplier_code}
                  type="button"
                  className={supplier.supplier_code === selectedSupplier ? 'selected' : ''}
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

        <section className="analysis-main">
          <div className="toolbar-row">
            {selectedSupplier && (
              <button type="button" className="secondary-button supplier-change-button" onClick={() => selectSupplier('')}>
                &laquo; {suppliers.find((s) => s.supplier_code === selectedSupplier)?.supplier_name || selectedSupplier}
              </button>
            )}
            <input
              className="product-search-input"
              placeholder="Search supplier products..."
              value={productSearch}
              onChange={(event) => setProductSearch(event.target.value)}
              disabled={!selectedSupplier}
            />
            <label className="stock-only-filter">
              <input type="checkbox" checked={onlyAvailable} onChange={(event) => setOnlyAvailable(event.target.checked)} />
              In stock only
            </label>
          </div>

          <div className="analysis-top-row">
            <div className="product-list-panel">
              <div className="product-list-header">
                <div className={`status-line ${productStatus.state}`}>{productStatus.message}</div>
                <MatchLegend />
              </div>
              <div className="table-wrap supplier-product-table">
                {products.length ? (
                  <table>
                    <thead>
                      <tr><th>Supplier product</th><th>Stock</th><th>Match</th></tr>
                    </thead>
                    <tbody>
                      {products.map((row) => (
                        <tr
                          key={row.supplier_stock_id}
                          className={row.supplier_stock_id === selectedStockId ? 'selected' : ''}
                          onClick={() => selectProduct(row)}
                          title={productTooltip(row)}
                        >
                          <td>{row.supplier_product_name || 'Unnamed product'}</td>
                          <td>{row.available_stock ?? '-'}</td>
                          <td><MatchBadge hasMapping={row.has_mapping} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : <div className="empty-state">{selectedSupplier ? 'No products for this supplier.' : 'Select a supplier on the left.'}</div>}
              </div>
            </div>

            <div className="match-summary-panel">
              <div className={`status-line ${detailStatus.state}`}>{detailStatus.message}</div>
              {match && (
                <ProductMatchGrid match={match} onPick={confirmMapping} />
              )}
              {dashboard && (
                <ProductSummaryPanel dashboard={dashboard} match={match} />
              )}
              {!selectedStockId && <div className="empty-state">Pick a supplier product to see its match and cross-store stock.</div>}
            </div>
          </div>

          <div className="store-detail-scroll">
            {dashboard && <ProductStoreRows dashboard={dashboard} />}
            {selectedStockId && !dashboard && <div className="empty-state">Resolve a product match above to see cross-store stock.</div>}
            {!selectedStockId && <div className="empty-state">Pick a supplier product to see its cross-store stock here.</div>}
          </div>
        </section>
      </div>
    </section>
  );
}

function MatchBadge({ hasMapping }) {
  return <span className={`match-dot ${hasMapping ? 'matched' : 'unmatched'}`} title={hasMapping ? 'Mapped' : 'Unmapped'} />;
}

function MatchLegend() {
  return (
    <div className="match-legend">
      <span><i className="dot matched" />Mapped</span>
      <span><i className="dot unmatched" />Unmapped</span>
    </div>
  );
}

function ProductMatchGrid({ match, onPick }) {
  if (match.product_code) {
    const name = match.exact_match?.product_name || match.supplier_stock?.supplier_product_name || match.product_code;
    return (
      <div className="product-match-grid">
        <div className="store-product-grid-wrap">
          <GridRow cols="1fr 100px" tag="span" className="active-row" cells={[name, match.product_code]} />
        </div>
      </div>
    );
  }
  const suggestions = match.suggestions || [];
  return (
    <div className="product-match-grid">
      {suggestions.length > 0 ? (
        <div className="store-product-grid-wrap">
          {suggestions.map((row) => (
            <GridRow
              key={`${row.store_id}-${row.product_code}`}
              cols="1fr 60px 55px"
              tag="span"
              className="suggestion-row"
              cells={[row.product_name, storeLabel(row), row.stock ?? '-']}
              onClick={() => onPick(row.product_code)}
            />
          ))}
        </div>
      ) : <span className="no-suggestions">No suggestions found.</span>}
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

function ProductSummaryPanel({ dashboard, match }) {
  const rows = dashboard.all_store_stock || [];
  const totalStock = rows.reduce((sum, row) => sum + Number(row.total_stock || 0), 0);

  return (
    <div className="product-summary">
      <div className="metric-grid">
        <Metric label="Product" value={dashboard.product_code} />
        <Metric label="Stores" value={rows.length} />
        <Metric label="Total Stock" value={totalStock} />
        <Metric label="Match" value={match?.match_status || '-'} />
      </div>
      <AllStoreStockPanel rows={rows} />
    </div>
  );
}

function ProductStoreRows({ dashboard }) {
  const groups = groupDashboardByStore(dashboard);
  return (
    <div className="store-row-grid product-store-rows">
      {groups.map((group, index) => (
        <ProductStoreRow key={group.store.store_id} group={group} colorIndex={index} />
      ))}
    </div>
  );
}

function ProductStoreColumnHeaders() {
  return (
    <div className="store-column-headers product-store-columns">
      <span className="store-header-cell" />
      <div className="header-cell">
        <div className="header-cell-title">Stock</div>
        <GridRow cols={STOCK_COLS} cells={['Product', 'Unit', 'Stock']} tag="span" />
      </div>
      <div className="header-cell">
        <div className="header-cell-title">3-Month Trend</div>
      </div>
      <div className="header-cell">
        <div className="header-cell-title">Batch</div>
        <GridRow cols={BATCH_COLS} cells={['Exp', 'Stk', 'MRP', 'Batch No']} tag="span" />
      </div>
      <div className="header-cell">
        <div className="header-cell-title">Purchase</div>
        <GridRow cols={PURCHASE_COLS} cells={['Qty', 'Free', 'GRN Date', 'GRN No', 'Supplier']} tag="span" />
      </div>
      <div className="header-cell">
        <div className="header-cell-title">Sales</div>
        <GridRow cols={SALES_COLS} cells={['Qty', 'Date', 'Bill No', 'Dis%', 'Customer', 'MRP']} tag="span" />
      </div>
    </div>
  );
}

function ProductStoreRow({ group, colorIndex }) {
  const storeColor = STORE_COLORS[colorIndex % STORE_COLORS.length];
  const { store, batches, purchases, sales, movement } = group;
  const label = storeLabel(store);
  return (
    <article className="store-data-row" style={{ '--store-color': storeColor }}>
      <div className="store-row-header-bar" title={store.store_name}>
        <span className="store-row-header-name">{label}</span>
        <span className="store-row-header-product">Showing: {store.product_name || '-'}</span>
      </div>

      <ProductStoreColumnHeaders />

      <div className="store-row-grid-body product-store-columns">
        <div className="store-row-label">
          {label.split('').map((char, index) => <strong key={index}>{char}</strong>)}
        </div>

        <section className="row-cell stock-cell">
          <div className="store-product-grid-wrap">
            <GridRow
              cols={STOCK_COLS}
              tag="span"
              className="active-row"
              cells={[store.product_name || '-', store.sale_unit || store.unit_description || '-', store.total_stock ?? 0]}
            />
          </div>
        </section>

        <section className="row-cell trend-cell">
          <MonthlyMovementChart rows={movement} />
        </section>

        <RowDataCell
          className="batch-table"
          cols={BATCH_COLS}
          emptyMessage="No batch details."
          rows={batches.slice(0, 20).map((row) => [formatDate(row.expirydate), row.stock ?? '-', row.mrp ?? '-', row.batchcode || '-'])}
        />
        <RowDataCell
          className="purchase-table"
          cols={PURCHASE_COLS}
          emptyMessage="No purchase details."
          rows={purchases.slice(0, 20).map((row) => [row.qty ?? '-', row.free ?? 0, formatDate(row.grndate), row.grn_no || '-', row.supplier || '-'])}
        />
        <RowDataCell
          className="sales-table"
          cols={SALES_COLS}
          emptyMessage="No sales details."
          rows={sales.slice(0, 20).map((row) => [row.qty ?? '-', formatDate(row.bill_date), row.bill_no || '-', row.discount ?? 0, row.customer_name || '-', row.mrp ?? '-'])}
        />
      </div>
    </article>
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

function Metric({ label, value }) {
  return (
    <div className="metric-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function AllStoreStockPanel({ rows }) {
  return (
    <DataTable
      className="all-store-stock-table"
      status={{ state: 'idle', message: 'All store stock details' }}
      columns={['Store', 'Product', 'Stock', 'MRP', 'PTR']}
      rows={rows.map((row) => [storeLabel(row), row.product_name || '-', row.total_stock ?? 0, row.mrp ?? '-', row.ptr ?? '-'])}
    />
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




































