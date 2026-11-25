import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { login as loginRequest, logout as logoutRequest, currentUser, devSkipLogin } from '../services/authService.js';
import { listStores, listTenants } from '../services/directoryService.js';
import {
  clearSession,
  consumeSessionEndReason,
  getSession,
  UNAUTHORIZED_EVENT,
} from '../services/sessionStore.js';
import { loadSettings, saveSettings } from '../services/settingsStore.js';
import { reconcileWorkspace, selectStore, selectTenant, workspaceFromLogin } from '../services/workspaceSelection.js';

const AuthContext = createContext(null);
const MAX_TIMER_MS = 2147483647;

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => currentUser() || devSkipLogin());
  const [notice, setNotice] = useState(() => consumeSessionEndReason());
  const [error, setError] = useState(null);
  const [isAuthenticating, setIsAuthenticating] = useState(false);
  const [workspace, setWorkspace] = useState(() => workspaceFromLogin(loadSettings(), currentUser()));
  const [tenants, setTenants] = useState([]);
  const [stores, setStores] = useState([]);
  const [directoryError, setDirectoryError] = useState(null);
  const [directoryLoading, setDirectoryLoading] = useState(false);

  useEffect(() => {
    const onUnauthorized = (event) => {
      clearSession();
      setUser(null);
      setTenants([]);
      setStores([]);
      setDirectoryError(null);
      setNotice(event.detail?.message || 'Your session is no longer valid. Sign in again.');
    };
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, []);

  useEffect(() => {
    if (!user) return undefined;
    const session = getSession();
    if (!session) {
      setUser(null);
      setNotice(consumeSessionEndReason() || 'Token expired');
      return undefined;
    }
    if (session.expiresAt == null) return undefined;
    const delay = session.expiresAt - Date.now() - 1000;
    let cancelled = false;
    const timer = setTimeout(() => {
      logoutRequest().finally(() => {
        if (cancelled) return;
        setUser(null);
        setTenants([]);
        setStores([]);
        setNotice('Token expired');
      });
    }, Math.max(0, Math.min(delay, MAX_TIMER_MS)));
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [user]);

  useEffect(() => {
    if (!user) {
      setTenants([]);
      setStores([]);
      setDirectoryLoading(false);
      return undefined;
    }
    let cancelled = false;
    setDirectoryLoading(true);
    setDirectoryError(null);
    Promise.all([listTenants(), listStores()])
      .then(([tenantRows, storeRows]) => {
        if (cancelled) return;
        setTenants(tenantRows);
        setStores(storeRows);
        setWorkspace((current) => {
          const next = reconcileWorkspace(current, user, tenantRows, storeRows);
          saveSettings(next);
          return next;
        });
      })
      .catch((err) => {
        if (cancelled) return;
        setDirectoryError(err?.message || 'Could not load tenants');
      })
      .finally(() => {
        if (!cancelled) setDirectoryLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [user]);

  const login = useCallback(async (username, password) => {
    setIsAuthenticating(true);
    setError(null);
    setNotice(null);
    try {
      const loggedInUser = await loginRequest(username, password);
      const next = workspaceFromLogin(loadSettings(), loggedInUser);
      saveSettings(next);
      setWorkspace(next);
      setUser(loggedInUser);
      return loggedInUser;
    } catch (err) {
      setError(err.message || 'Login failed');
      throw err;
    } finally {
      setIsAuthenticating(false);
    }
  }, []);

  const logout = useCallback(async () => {
    await logoutRequest();
    setUser(null);
    setTenants([]);
    setStores([]);
    setDirectoryError(null);
    setNotice(null);
    setError(null);
  }, []);

  const changeTenant = useCallback((tenantId) => {
    setWorkspace((current) => {
      const next = selectTenant(current, tenantId, stores);
      saveSettings(next);
      return next;
    });
  }, [stores]);

  const changeStore = useCallback((storeId) => {
    setWorkspace((current) => {
      const store = stores.find((row) => String(row.store_id) === String(storeId)) || null;
      const next = selectStore(current, store);
      saveSettings(next);
      return next;
    });
  }, [stores]);

  const value = useMemo(
    () => ({
      user,
      isAuthenticated: Boolean(user),
      isAuthenticating,
      error,
      notice,
      login,
      logout,
      tenantId: workspace.tenantId || '',
      storeId: workspace.storeId || '',
      storeName: workspace.storeName || '',
      tenants,
      stores,
      directoryError,
      directoryLoading,
      changeTenant,
      changeStore,
    }),
    [
      user,
      isAuthenticating,
      error,
      notice,
      login,
      logout,
      workspace,
      tenants,
      stores,
      directoryError,
      directoryLoading,
      changeTenant,
      changeStore,
    ]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider');
  return ctx;
}
