const SETTINGS_KEY = 'nexora.desktop.settings';
const SESSION_KEY = 'nexora.desktop.session';

const defaultSettings = {
  serverMode: 'LAN',
  // Default to the HO server on the LAN so a fresh install connects with no
  // manual Settings step. Override per-PC in Settings for remote/static-IP stores.
  apiBaseUrl: 'http://192.168.10.80:8000',
  bootstrapUrl: '',
  tenantId: '',
  storeId: '',
  storeName: '',
  storeOrder: [],
  // Device-activation id (from POST /api/desktop-client/activate/request). The
  // app polls /config by this id until HO approves and assigns the store.
  clientId: '',
  similarSearchChars: 6,
  themePreference: 'light'
};

function todayKey() {
  return new Date().toISOString().slice(0, 10);
}

export function loadSettings() {
  try {
    return { ...defaultSettings, ...JSON.parse(localStorage.getItem(SETTINGS_KEY) || '{}') };
  } catch {
    return defaultSettings;
  }
}

export function saveSettings(settings) {
  const next = { ...defaultSettings, ...settings };
  localStorage.setItem(SETTINGS_KEY, JSON.stringify(next));
  return next;
}

export function loadSession() {
  try {
    const session = JSON.parse(localStorage.getItem(SESSION_KEY) || 'null');
    if (!session || session.loginDate !== todayKey()) {
      localStorage.removeItem(SESSION_KEY);
      return null;
    }
    return session;
  } catch {
    localStorage.removeItem(SESSION_KEY);
    return null;
  }
}

export function saveSession(payload) {
  const session = { ...payload, loginDate: todayKey() };
  localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  return session;
}

export function clearSession() {
  localStorage.removeItem(SESSION_KEY);
}
