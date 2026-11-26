// Store-side order cache sync. When HO's Order Process generates a store's
// order it (re)builds that store's order cache (backend legacy_order/
// order_cache). A purchase-manager login on the store PC polls its own
// store's cache through the store-user-readable GET .../order-cache/{store}/view
// and keeps a local copy (electron main.cjs orderCache:write) whenever HO's
// stamp changes, so the newest order's cache always lands on the PC where
// that store's PM is signed in. Super-admin sessions are skipped here: they
// are not tied to one store (the Procurement workspace still syncs whichever
// store it opens, on demand). The copy is what orderCacheLocal.jsx serves
// By Supplier / Live Stock / compare from.
import { useEffect } from 'react';
import { api } from './api/client.js';
import { createOrderCache } from './orderCacheLocal.jsx';

const POLL_MS = 2 * 60 * 1000;

let currentSession = null;

export const orderCache = createOrderCache({
  fetchView: (store, have) => api.orderCacheView(store, currentSession, have),
  fetchStates: (store) => api.legacyOrderLineStates(store, currentSession),
});

function pmStoreCodes(session) {
  const roles = session?.user?.roles || [];
  const codes = roles
    .filter((role) => String(role?.role_name || role?.role || '').toLowerCase().includes('purchase'))
    .map((role) => String(role?.store_code || '').trim().toUpperCase())
    .filter(Boolean);
  return [...new Set(codes)];
}

export function useOrderCacheSync(session, enabled) {
  currentSession = session;
  const token = session?.token || session?.accessToken || session?.access_token;
  const stores = enabled ? pmStoreCodes(session).join(',') : '';
  useEffect(() => {
    if (!token || !stores || !window.nexoraDesktop?.orderCache) return undefined;
    let stopped = false;
    const run = async () => {
      for (const store of stores.split(',')) {
        if (stopped) return;
        try { await orderCache.sync(store, true); } catch (err) { console.info(`[order-cache] ${store}: ${err?.message || err}`); }
      }
    };
    run();
    const timer = setInterval(run, POLL_MS);
    return () => { stopped = true; clearInterval(timer); };
    // session object identity changes on every render-level refresh; the
    // token + store list are what actually decide whether to (re)start.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, stores]);
}
