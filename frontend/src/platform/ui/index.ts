// Re-exports existing components/common/* under the platform's Uni* naming
// so new modules can `import { UniEmptyState } from '../../platform/ui'`
// alongside net-new components, without moving/renaming files that dozens of
// existing pages already import directly (a mechanical, high-blast-radius
// rename for zero functional benefit).
export { EmptyState as UniEmptyState } from '../../components/common/EmptyState'
export { ErrorState as UniErrorState } from '../../components/common/ErrorState'
export { Skeleton as UniSkeleton } from '../../components/common/Skeleton'
export { TableSkeleton as UniTableSkeleton } from '../../components/common/TableSkeleton'
export { PageHeader as UniPageHeader } from '../../components/common/PageHeader'
export { StatusBadge as UniStatusBadge } from '../../components/common/StatusBadge'
export { ThemeToggle as UniThemeToggle } from '../../components/common/ThemeToggle'

export { UniGrid } from './UniGrid'
export type { UniGridColumn } from './UniGrid'
export { UniLoadingOverlay } from './UniLoadingOverlay'
export { UniNotification } from './UniNotification'
export { notify, notificationService } from './notificationService'
export type { Notification, NotificationVariant } from './notificationService'
export { BaseWorkspace } from './BaseWorkspace'
export { useBaseModule } from './useBaseModule'
