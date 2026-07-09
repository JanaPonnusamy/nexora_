import type { ModuleDefinition } from '../modules/types'

interface WorkspaceTabsProps {
  openModules: ModuleDefinition[]
  activeModuleId?: string
  onSelect: (moduleId: string) => void
  onClose: (moduleId: string) => void
}

/**
 * Open-module tab strip. Opening a module from the nav rail pushes/activates
 * a tab here; closing a tab is what triggers ModuleHost's unmount (and thus
 * the module's dispose() lifecycle hook).
 */
export function WorkspaceTabs({ openModules, activeModuleId, onSelect, onClose }: WorkspaceTabsProps) {
  if (openModules.length === 0) return null

  return (
    <div className="platform-tabs" role="tablist">
      {openModules.map((module) => (
        <div
          key={module.id}
          role="tab"
          aria-selected={module.id === activeModuleId}
          className={`platform-tabs__tab${module.id === activeModuleId ? ' is-active' : ''}`}
          onClick={() => onSelect(module.id)}
        >
          {module.icon && <i className={`bi ${module.icon}`} aria-hidden="true" />}
          <span className="platform-tabs__label">{module.title}</span>
          <button
            type="button"
            className="platform-tabs__close"
            aria-label={`Close ${module.title}`}
            onClick={(event) => {
              event.stopPropagation()
              onClose(module.id)
            }}
          >
            <i className="bi bi-x" aria-hidden="true" />
          </button>
        </div>
      ))}
    </div>
  )
}
