import ReportsPage from '../../pages/ReportsPage'
import { logger } from '../logging/Logger'
import type { ModuleDefinition } from './types'

/**
 * Phase 2.4 proof-of-concept: wraps the existing Reports page (left
 * completely untouched — still also reachable at the live /reports route)
 * as a real ModuleDefinition, to validate the module framework end-to-end
 * before any further module migration. Reports was chosen because it's the
 * simplest existing module: one page, no sub-tabs, no local state machine.
 */
export const reportsModule: ModuleDefinition = {
  id: 'reports',
  title: 'Reports',
  icon: 'bi-bar-chart',
  nav: {
    id: 'reports',
    label: 'Reports',
    icon: 'bi-bar-chart',
    group: 'System',
    path: '/reports',
    capability: 'REPORTS',
  },
  component: ReportsPage,
  lifecycle: {
    initialize: () => logger.info('reports', 'Module initialized'),
    dispose: () => logger.info('reports', 'Module disposed'),
  },
}
