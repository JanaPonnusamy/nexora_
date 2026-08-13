import type { Module } from '../../types/module'
import { StatusBadge } from '../common/StatusBadge'
import { ModuleActions } from './ModuleActions'
import { DataTable, type DataTableColumn } from '../common/DataTable'

interface ModuleTableProps {
  modules: Module[]
  onView: (module: Module) => void
  onEdit: (module: Module) => void
}

export function ModuleTable({ modules, onView, onEdit }: ModuleTableProps) {
  const columns: DataTableColumn<Module>[] = [
    {
      key: 'module_code',
      header: 'Module Code',
      sortable: true,
      accessor: (module) => <code>{module.module_code}</code>,
    },
    {
      key: 'module_name',
      header: 'Module Name',
      sortable: true,
      accessor: (module) => <span className="fw-medium">{module.module_name}</span>,
    },
    {
      key: 'description',
      header: 'Description',
      sortable: true,
      accessor: (module) => <span className="text-secondary">{module.description ?? '—'}</span>,
    },
    {
      key: 'is_active',
      header: 'Status',
      sortable: true,
      accessor: (module) => <StatusBadge active={module.is_active} />,
    },
    {
      key: 'actions',
      header: 'Actions',
      align: 'right',
      accessor: (module) => (
        <ModuleActions
          moduleName={module.module_name}
          onView={() => onView(module)}
          onEdit={() => onEdit(module)}
        />
      ),
    },
  ]

  return (
    <div className="d-none d-md-block">
      <DataTable
        columns={columns}
        data={modules}
        getRowId={(module) => module.module_id}
        onRowClick={onView}
        pageSize={10}
      />
    </div>
  )
}
