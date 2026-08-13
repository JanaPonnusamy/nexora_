import type { ReactNode } from 'react'
import { DataTable, type DataTableColumn } from '../../components/common/DataTable'

export interface UniGridColumn<T> {
  key: string
  header: string
  render?: (row: T) => ReactNode
  align?: 'start' | 'end' | 'center'
  width?: string
}

interface UniGridProps<T> {
  columns: UniGridColumn<T>[]
  rows: T[]
  getRowId: (row: T) => string
  isLoading?: boolean
  emptyTitle?: string
  emptyDescription?: string
  onRowClick?: (row: T) => void
  activeRowId?: string
}

/** Lightweight platform adapter for the application-wide DataTable. */
export function UniGrid<T>({
  columns,
  rows,
  getRowId,
  isLoading,
  emptyTitle = 'No data',
  emptyDescription,
  onRowClick,
  activeRowId,
}: UniGridProps<T>) {
  const dataTableColumns: DataTableColumn<T>[] = columns.map((column) => ({
    key: column.key,
    header: column.header,
    accessor: column.render,
    align:
      column.align === 'start' ? 'left' : column.align === 'end' ? 'right' : column.align,
    width: column.width,
    sortable: true,
  }))

  return (
    <DataTable
      columns={dataTableColumns}
      data={rows}
      getRowId={getRowId}
      isLoading={isLoading}
      emptyText={
        <>
          <strong className="d-block text-body">{emptyTitle}</strong>
          {emptyDescription && <span>{emptyDescription}</span>}
        </>
      }
      onRowClick={onRowClick}
      activeRowId={activeRowId}
      pageSize={0}
    />
  )
}
