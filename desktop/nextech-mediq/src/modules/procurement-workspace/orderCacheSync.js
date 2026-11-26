// Store-side order cache sync -- ported from supplier-stock-client's
// orderCacheSync.js; only the HO fetchers differ (direct services, the
// session is read by the API client itself). When HO's Order Process builds a
// store's order cache, a purchase-manager login polls its own store(s) and
// keeps a local copy (electron orderCache:write), which orderCacheLocal.jsx
// serves By Supplier / Live Stock / compare from. Logins with no purchase
// role skip the poll; the Procurement workspace still syncs whichever store
// it opens, on demand.
import { useEffect } from 'react';
import { legacyOrderCacheView, legacyOrderLineStates } from '../../services/legacyOrderService.js';
import { createOrderCache } from './orderCacheLocal.jsx';

const POLL_MS = 2 * 60 * 1000;

export const orderCache = createOrderCache({
  fetchView: (store, have) => legacyOrderCacheView(store, have),
  fetchStates: (store) => legacyOrderLineStates(store),
});

function pmStoreCodes(user) {
  const roles = user?.roles || [];
  const codes = roles
    .filter((role) => String(role?.role_name || role?.role || '').toLowerCase().includes('purchase'))
    .map((role) => String(role?.store_code || '').trim().toUpperCase())
    .filter(Boolean);
  return [...new Set(codes)];
}

export function useOrderCacheSync(user) {
  const stores = pmStoreCodes(user).join(',');
  useEffect(() => {
    if (!stores || !window.nexoraDesktop?.orderCache) return undefined;
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
  }, [stores]);
}
