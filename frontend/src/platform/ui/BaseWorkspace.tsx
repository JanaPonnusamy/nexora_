import type { ReactNode } from 'react'
import { PageHeader } from '../../components/common/PageHeader'
import { ErrorState } from '../../components/common/ErrorState'
import { UniLoadingOverlay } from './UniLoadingOverlay'

interface BaseWorkspaceProps {
  title: string
  breadcrumb?: string[]
  isLoading?: boolean
  error?: string | null
  onRetry?: () => void
  children: ReactNode
}

/**
 * Common chrome most simple modules need: a page header, a loading overlay
 * over in-flight re-fetches, and a shared error state on failure — cuts the
 * boilerplate every module currently reimplements on its own (see Reports,
 * Stock Availability). Modules with more elaborate layouts (Purchase
 * Manager's master/detail, docked panels) build directly on
 * DockGroup/UniGrid instead of this scaffold.
 */
export function BaseWorkspace({ title, breadcrumb, isLoading, error, onRetry, children }: BaseWorkspaceProps) {
  return (
    <div className="base-workspace">
      <PageHeader title={title} breadcrumb={breadcrumb ?? [title]} />
      {error ? (
        <ErrorState description={error} onRetry={onRetry} />
      ) : (
        <div className="base-workspace__body">
          {children}
          {isLoading && <UniLoadingOverlay fullPage />}
        </div>
      )}
    </div>
  )
}
