import PurchaseWorkspacePage from '../../pages/procurement/PurchaseWorkspacePage'
import { logger } from '../logging/Logger'
import type { ModuleDefinition } from './types'

/**
 * Phase 3 (Minimum Viable Desktop): wraps the existing, already-optimized
 * Purchase Manager workspace unmodified — the same component still serving
 * the live /procurement/workspace browser route, no behavior change.
 *
 * PurchaseWorkspacePage already has its own tenant/store/refresh pickers
 * built into its top bar (it reads `?tenant=&refresh=` from the URL only as
 * an optional deep-link convenience — see its useSearchParams() usage), so
 * it independently covers refresh selection through Final Qty save without
 * needing RefreshLauncherPage as a separate step. Wrapping it alone is the
 * leanest MVD: one module, no URL-query handoff between two screens to
 * replicate inside the tab-based workspace host.
 */
export const purchaseManagerModule: ModuleDefinition = {
  id: 'purchase-manager',
  title: 'Purchase Manager',
  icon: 'bi-cart-check',
  nav: {
    id: 'purchase-manager',
    label: 'Purchase Manager',
    icon: 'bi-cart-check',
    group: 'Procurement',
    path: '/procurement/workspace',
    capability: 'PROCUREMENT_WORKSPACE',
  },
  component: PurchaseWorkspacePage,
  lifecycle: {
    initialize: () => logger.info('purchase-manager', 'Module initialized'),
    dispose: () => logger.info('purchase-manager', 'Module disposed'),
  },
}
