import React, { useEffect, useState } from 'react';
import { PageLayout } from '../../layouts/PageLayout.jsx';
import { useAuth } from '../../contexts/AuthContext.jsx';
import { useTheme } from '../../themes/ThemeContext.jsx';
import { THEME_IDS, themeById } from '../../themes/themeLogic.js';
import { GlassStatusBadge } from '../../ui/glass.jsx';
import { DEFAULT_LAN_URL, DEFAULT_PUBLIC_URL, loadSettings, saveSettings } from '../../services/settingsStore.js';
import { TenantMailSettings } from './TenantMailSettings.jsx';

export function SettingsPage() {
  const { user, tenantId, tenants } = useAuth();
  const tenant = (tenants || []).find((t) => String(t.tenant_id) === String(tenantId));
  const { preference, setPreference } = useTheme();
  const [version, setVersion] = useState('0.1.0');
  const [platform, setPlatform] = useState('');
  const [lanUrl, setLanUrl] = useState(() => loadSettings().lanUrl || DEFAULT_LAN_URL);
  const [publicUrl, setPublicUrl] = useState(() => loadSettings().publicUrl || DEFAULT_PUBLIC_URL);
  const [savedAt, setSavedAt] = useState(null);

  function handleSaveConnection() {
    saveSettings({ lanUrl: lanUrl.trim(), publicUrl: publicUrl.trim() });
    setSavedAt(Date.now());
  }

  function handleResetConnection() {
    setLanUrl(DEFAULT_LAN_URL);
    setPublicUrl(DEFAULT_PUBLIC_URL);
    saveSettings({ lanUrl: DEFAULT_LAN_URL, publicUrl: DEFAULT_PUBLIC_URL });
    setSavedAt(Date.now());
  }

  useEffect(() => {
    const app = window.nextechMediq?.app;
    if (!app) return undefined;
    let cancelled = false;
    Promise.all([
      typeof app.getVersion === 'function' ? app.getVersion() : Promise.resolve(''),
      typeof app.getPlatformInfo === 'function' ? app.getPlatformInfo() : Promise.resolve(null),
    ]).then(([appVersion, info]) => {
      if (cancelled) return;
      if (appVersion) setVersion(String(appVersion));
      if (info?.platform) setPlatform(`${info.platform} · Electron ${info.electron || ''}`.trim());
    }).catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  const name = user?.full_name || user?.username || 'Signed-in operator';

  return (
    <PageLayout title="Settings">
      <div className="ntm-card-grid">
        <article className="ntm-card">
          <h2>Session</h2>
          <p className="ntm-metric ntm-metric--text">{name}</p>
        </article>
        <article className="ntm-card">
          <h2>Application</h2>
          <p className="ntm-metric ntm-metric--text">{version}</p>
          <p className="ntm-card__hint">{platform || 'NexTech MediQ Workspace'}</p>
        </article>
      </div>
      <h2 className="ntm-section-title">Connection</h2>
      <div className="ntm-card ntm-form">
        <p className="ntm-form__hint">
          LAN is tried first (fast, no internet needed on-site); the public address is used only when the LAN
          address can&apos;t be reached. Changes apply immediately, no restart needed.
        </p>
        <div className="ntm-field">
          <label htmlFor="ntm-ho-lan">LAN address</label>
          <input
            id="ntm-ho-lan"
            type="text"
            value={lanUrl}
            placeholder={DEFAULT_LAN_URL}
            onChange={(event) => setLanUrl(event.target.value)}
          />
        </div>
        <div className="ntm-field">
          <label htmlFor="ntm-ho-public">Public / internet address</label>
          <input
            id="ntm-ho-public"
            type="text"
            value={publicUrl}
            placeholder={DEFAULT_PUBLIC_URL}
            onChange={(event) => setPublicUrl(event.target.value)}
          />
        </div>
        <div className="ntm-form__actions">
          <button type="button" className="ntm-button ntm-button--primary" onClick={handleSaveConnection}>
            Save
          </button>
          <button type="button" className="ntm-button" onClick={handleResetConnection}>
            Reset to defaults
          </button>
          {savedAt ? <span className="ntm-form__hint">Saved.</span> : null}
        </div>
      </div>

      <h2 className="ntm-section-title">Supplier Mail Import</h2>
      <TenantMailSettings tenantId={tenantId} tenantName={tenant?.tenant_name?.trim()} />

      <h2 className="ntm-section-title">Theme</h2>
      <div className="ntm-theme-grid">
        {THEME_IDS.map((id) => {
          const item = themeById(id);
          const active = preference === id;
          return (
            <button
              key={id}
              type="button"
              className={`ntm-glass ntm-theme-swatch${active ? ' is-active' : ''}`}
              onClick={() => setPreference(id)}
              aria-pressed={active}
            >
              <div className="ntm-theme-swatch__bar" aria-hidden="true">
                <span style={{ background: item.bg }} />
                <span style={{ background: item.accent }} />
                <span style={{ background: item.cyan }} />
                <span style={{ background: item.tableBg }} />
              </div>
              <strong>{item.label}</strong>
              {active ? <GlassStatusBadge tone="info">Active</GlassStatusBadge> : <em>{item.mode}</em>}
            </button>
          );
        })}
      </div>
    </PageLayout>
  );
}
