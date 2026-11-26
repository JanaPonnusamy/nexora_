import React from 'react';
import { useAuth } from '../contexts/AuthContext.jsx';
import { LoginPage } from './LoginPage.jsx';

// Trusts the backend, not the renderer, to decide what an authenticated
// user may access — this guard only decides "show login vs. show app,"
// per Phase 6 §6: the backend is the sole authority on tenant/store
// authorization for every subsequent API call this app makes.
export function RequireAuth({ children }) {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) {
    return <LoginPage />;
  }
  return children;
}
