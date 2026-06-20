import type { Module } from '../../types/module'
import { StatusBadge } from '../common/StatusBadge'
import { ModuleActions } from './ModuleActions'

interface ModuleCardListProps {
  modules: Module[]
  onView: (module: Module) => void
  onEdit: (module: Module) => void
}

export function ModuleCardList({ modules, onView, onEdit }: ModuleCardListProps) {
  return (
    <div className="d-md-none vstack gap-2">
      {modules.map((module) => (
        <div className="card list-card" key={module.module_id} onClick={() => onView(module)}>
          <div className="card-body">
            <div className="d-flex justify-content-between align-items-start gap-2">
              <div className="min-w-0">
                <div className="fw-semibold text-truncate">{module.module_name}</div>
                <div className="text-secondary small">
                  <code>{module.module_code}</code>
                </div>
              </div>
              <StatusBadge active={module.is_active} />
            </div>
            <div className="text-secondary small mt-2 text-truncate">
              {module.description ?? '—'}
            </div>
            <div className="mt-3">
              <ModuleActions
                moduleName={module.module_name}
                onView={() => onView(module)}
                onEdit={() => onEdit(module)}
              />
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
