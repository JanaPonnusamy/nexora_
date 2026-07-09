import { EmptyState } from '../../components/common/EmptyState'
import { ErrorBoundary } from '../errors/ErrorBoundary'
import { ModuleHost } from '../modules/ModuleHost'
import type { ModuleDefinition } from '../modules/types'

interface WorkspaceHostProps {
  activeModule: ModuleDefinition | undefined
}

/**
 * The module host area — renders whichever module is active. A module that
 * wants internal docked panels (grid + decision panel, grid + charts, ...)
 * builds that itself with DockGroup/DockPanelItem/DockSeparator; this is
 * just the outer slot the shell hands the module.
 */
export function WorkspaceHost({ activeModule }: WorkspaceHostProps) {
  if (!activeModule) {
    return (
      <div className="platform-workspace-host platform-workspace-host--empty">
        <EmptyState
          icon="bi-window-stack"
          title="No module open"
          description="Choose a module from the navigation rail to get started."
        />
      </div>
    )
  }

  return (
    <div className="platform-workspace-host">
      <ErrorBoundary scope={activeModule.id}>
        <ModuleHost definition={activeModule} />
      </ErrorBoundary>
    </div>
  )
}
