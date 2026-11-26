import React, { useEffect, useState } from 'react';
import { BrandLockup } from '../components/BrandLockup.jsx';
import { useAuth } from '../contexts/AuthContext.jsx';
import { Icon } from '../ui/icons.jsx';
import { Icon3D } from '../ui/icons3d.jsx';

const FEATURE_HIGHLIGHTS = [
  { icon: 'inventory', label: 'Inventory' },
  { icon: 'procurement', label: 'Procurement' },
  { icon: 'reports', label: 'Sales & Reports' },
  { icon: 'spark', label: 'AI Intelligence' },
];

export function LoginPage() {
  const { login, isAuthenticating, error, notice } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [remember, setRemember] = useState(true);
  const [version, setVersion] = useState('0.1.0');

  useEffect(() => {
    const read = window.nextechMediq?.app?.getVersion;
    if (typeof read !== 'function') return undefined;
    let cancelled = false;
    read().then((value) => {
      if (!cancelled && value) setVersion(String(value));
    }).catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleSubmit(event) {
    event.preventDefault();
    try {
      await login(username, password, { remember });
    } catch {
      // The message is already on useAuth().error.
    }
  }

  return (
    <div className="ntm-login">
      <div className="ntm-login__stage">
        <section className="ntm-login__brandpane" aria-hidden="true">
          <div className="ntm-login__brandpane-lockup">
            <BrandLockup variant="lockup" forceTheme="dark" className="ntm-login__brandpane-logo" />
          </div>
          <p className="ntm-login__eyebrow">
            <Icon name="spark" size={14} />
            AI-Powered Intelligent Pharmaceutical Workspace
          </p>
          <h1 className="ntm-login__headline">
            Run your pharmaceutical business with clarity and intelligence.
          </h1>
          <p className="ntm-login__subcopy">
            A single workspace for inventory, procurement, supplier intelligence,
            and AI-assisted decisions across every branch.
          </p>
          <ul className="ntm-login__features">
            {FEATURE_HIGHLIGHTS.map((feature) => (
              <li key={feature.label} className="ntm-login__feature">
                <span className="ntm-login__feature-icon">
                  <Icon3D name={feature.icon} size={34} />
                </span>
                <span>{feature.label}</span>
              </li>
            ))}
          </ul>
        </section>

        <section className="ntm-login__panel">
          <div className="ntm-login__panel-inner">
            <div className="ntm-login__brand">
              <BrandLockup variant="lockup" forceTheme="light" />
            </div>
            <h2 className="ntm-login__welcome">Welcome back</h2>
            <p className="ntm-login__tagline">Sign in to your workspace</p>

            <form onSubmit={handleSubmit} className="ntm-login__form" noValidate>
              <label className="ntm-login__field">
                <span className="ntm-login__field-label">Username</span>
                <span className="ntm-login__input-shell">
                  <Icon name="user" size={16} className="ntm-login__input-icon" />
                  <input
                    type="text"
                    name="username"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    autoFocus
                    autoComplete="username"
                    placeholder="Enter your username"
                    required
                  />
                </span>
              </label>

              <label className="ntm-login__field">
                <span className="ntm-login__field-label">Password</span>
                <span className="ntm-login__input-shell">
                  <Icon name="lock" size={16} className="ntm-login__input-icon" />
                  <input
                    type={showPassword ? 'text' : 'password'}
                    name="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    autoComplete="current-password"
                    placeholder="Enter your password"
                    required
                  />
                  <button
                    type="button"
                    className="ntm-login__reveal"
                    onClick={() => setShowPassword((value) => !value)}
                    aria-pressed={showPassword}
                    aria-label={showPassword ? 'Hide password' : 'Show password'}
                    title={showPassword ? 'Hide password' : 'Show password'}
                  >
                    <Icon name={showPassword ? 'eyeOff' : 'eye'} size={17} />
                  </button>
                </span>
              </label>

              <label className="ntm-login__remember">
                <input
                  type="checkbox"
                  checked={remember}
                  onChange={(e) => setRemember(e.target.checked)}
                />
                <span>Remember this device</span>
              </label>

              {notice ? <p className="ntm-login__notice" role="status">{notice}</p> : null}
              {error ? <p className="ntm-login__error" role="alert">{error}</p> : null}

              <button type="submit" className="ntm-login__submit" disabled={isAuthenticating}>
                {isAuthenticating ? (
                  <span className="ntm-login__spinner" aria-hidden="true" />
                ) : (
                  <Icon name="orders" size={16} />
                )}
                {isAuthenticating ? 'Signing in…' : 'Sign in'}
              </button>
            </form>

            <p className="ntm-login__footer">NexTech MediQ Workspace {version}</p>
          </div>
        </section>
      </div>
    </div>
  );
}
