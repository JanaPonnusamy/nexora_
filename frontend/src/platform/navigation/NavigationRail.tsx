import type { ModuleDefinition } from '../modules/types'
import { useAccess } from '../../hooks/useAccess'

interface NavigationRailProps {
  modules: ModuleDefinition[]
  activeModuleId?: string
  onSelect: (moduleId: string) => void
}

/**
 * Data-driven equivalent of components/sidebar/Sidebar.tsx's hardcoded
 * NAV_ENTRIES — modules register their own NavContribution instead of the
 * nav list being maintained separately from the module set. Grouped the same
 * way Sidebar groups related links; gating reuses the same useAccess() the
 * rest of the app already relies on.
 */
export function NavigationRail({ modules, activeModuleId, onSelect }: NavigationRailProps) {
  const { can } = useAccess()

  const visible = modules.filter((m) => !m.nav.capability || can(m.nav.capability))
  const groups = new Map<string, ModuleDefinition[]>()
  for (const module of visible) {
    const list = groups.get(module.nav.group) ?? []
    list.push(module)
    groups.set(module.nav.group, list)
  }

  if (visible.length === 0) {
    return (
      <aside className="platform-nav-rail">
        <div className="platform-nav-rail__empty">No modules registered yet.</div>
      </aside>
    )
  }

  return (
    <aside className="platform-nav-rail">
      <nav className="platform-nav-rail__nav">
        {[...groups.entries()].map(([group, groupModules]) => (
          <div key={group} className="platform-nav-rail__group">
            <div className="platform-nav-rail__group-title">{group}</div>
            {groupModules.map((module) => (
              <button
                key={module.id}
                type="button"
                className={`platform-nav-rail__link${module.id === activeModuleId ? ' active' : ''}`}
                title={module.title}
                onClick={() => onSelect(module.id)}
              >
                {module.icon && (
                  <i className={`bi ${module.icon} platform-nav-rail__icon`} aria-hidden="true" />
                )}
                <span className="platform-nav-rail__label">{module.title}</span>
              </button>
            ))}
          </div>
        ))}
      </nav>
    </aside>
  )
}
