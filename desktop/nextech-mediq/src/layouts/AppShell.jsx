import React, { useState } from 'react';
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { Sidebar } from './Sidebar.jsx';
import { TopBar } from './TopBar.jsx';
import { ModuleErrorBoundary } from '../components/ErrorBoundary.jsx';
import { useAuth } from '../contexts/AuthContext.jsx';
import { resolvePathForUser } from '../navigation/access.js';
import { loadCollapsed, saveCollapsed } from './sidebarState.js';
import { useOrderCacheSync } from '../modules/procurement-workspace/orderCacheSync.js';

function GuardedOutlet() {
  const { user } = useAuth();
  const location = useLocation();
  const redirect = resolvePathForUser(user, location.pathname);
  if (redirect && redirect !== location.pathname) return <Navigate to={redirect} replace />;
  return <Outlet />;
}

export function AppShell() {
  const [collapsed, setCollapsed] = useState(() => loadCollapsed());
  const { user } = useAuth();
  // Keep this PM's store order cache downloaded to this PC.
  useOrderCacheSync(user);

  function toggleCollapsed() {
    setCollapsed((value) => {
      const next = !value;
      saveCollapsed(next);
      return next;
    });
  }

  return (
    <div className={`ntm-shell${collapsed ? ' ntm-shell--collapsed' : ''}`}>
      <Sidebar collapsed={collapsed} onToggle={toggleCollapsed} />
      <div className="ntm-shell__main">
        <TopBar />
        <main className="ntm-shell__content">
          <ModuleErrorBoundary>
            <GuardedOutlet />
          </ModuleErrorBoundary>
        </main>
      </div>
    </div>
  );
}
