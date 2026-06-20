import type { Module } from '../../types/module'
import { StatusBadge } from '../common/StatusBadge'
import { ModuleActions } from './ModuleActions'

interface ModuleTableProps {
  modules: Module[]
  onView: (module: Module) => void
  onEdit: (module: Module) => void
}

export function ModuleTable({ modules, onView, onEdit }: ModuleTableProps) {
  return (
    <div className="table-responsive d-none d-md-block">
      <table className="table table-hover align-middle data-table">
        <thead>
          <tr>
            <th scope="col">Module Code</th>
            <th scope="col">Module Name</th>
            <th scope="col">Description</th>
            <th scope="col">Status</th>
            <th scope="col" className="text-end">Actions</th>
          </tr>
        </thead>
        <tbody>
          {modules.map((module) => (
            <tr key={module.module_id} className="data-row" onClick={() => onView(module)}>
              <td>
                <code>{module.module_code}</code>
              </td>
              <td className="fw-medium">{module.module_name}</td>
              <td className="text-secondary">{module.description ?? '—'}</td>
              <td>
                <StatusBadge active={module.is_active} />
              </td>
              <td className="text-end">
                <ModuleActions
                  moduleName={module.module_name}
                  onView={() => onView(module)}
                  onEdit={() => onEdit(module)}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
