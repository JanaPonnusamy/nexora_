import type { ReactNode } from 'react'
import { EmptyState } from '../../components/common/EmptyState'
import { UniLoadingOverlay } from './UniLoadingOverlay'

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

/**
 * Shared data grid — 5+ existing modules (Purchase Manager's ProductGrid,
 * Product Intelligence's IntelligenceGrid, Supplier Live Stock's table,
 * every platform-admin entity table, ...) each hand-roll their own
 * `<table>`. This is the reusable version new modules build on; existing
 * grids are not touched by this change.
 */
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
  return (
    <div className="uni-grid">
      <table className="table uni-grid__table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key} style={{ width: column.width, textAlign: column.align }}>
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const rowId = getRowId(row)
            return (
              <tr
                key={rowId}
                className={[
                  onRowClick ? 'uni-grid__row--clickable' : '',
                  rowId === activeRowId ? 'table-active' : '',
                ]
                  .filter(Boolean)
                  .join(' ')}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
              >
                {columns.map((column) => (
                  <td key={column.key} style={{ textAlign: column.align }}>
                    {column.render
                      ? column.render(row)
                      : String((row as Record<string, unknown>)[column.key] ?? '')}
                  </td>
                ))}
              </tr>
            )
          })}
        </tbody>
      </table>
      {isLoading && <UniLoadingOverlay fullPage />}
      {!isLoading && rows.length === 0 && (
        <EmptyState icon="bi-table" title={emptyTitle} description={emptyDescription} />
      )}
    </div>
  )
}
