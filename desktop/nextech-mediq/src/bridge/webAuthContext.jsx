// Stand-in for frontend/src/contexts/AuthContext.tsx.
// Embedded pages call useAuth() against this context. The value is mapped
// from the desktop session so pages see the same user shape the web app builds
// from /api/auth/me, without a second login.
import React, { createContext, useMemo } from 'react';
import { useAuth as useDesktopAuth } from '../contexts/AuthContext.jsx';
import { getSession } from '../services/sessionStore.js';
import { toWebUser } from './webUser.js';
import { NEXTECH_MEDIQ_HOST } from '@web/pages/quick-stock/mediqHost.ts';

export const AuthContext = createContext(undefined);

export function WebAuthBridge({ children }) {
  const desktop = useDesktopAuth();
  const value = useMemo(() => ({
    user: toWebUser(desktop.user, {
      tenantId: desktop.tenantId,
      storeId: desktop.storeId,
    }),
    token: getSession()?.token || null,
    host: NEXTECH_MEDIQ_HOST,
    isAuthenticated: Boolean(desktop.user),
    restoring: false,
    login: () => {},
    logout: () => {
      desktop.logout();
    },
  }), [desktop]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
