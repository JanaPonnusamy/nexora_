import { useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import './dataTable.css'

export type Alignment = 'left' | 'center' | 'right'
export type Density = 'compact' | 'comfortable'
export type SortDirection = 'asc' | 'desc' | null

export interface DataTableColumn<T> {
  /** Unique key identifying the column */
  key: string
  /** Header label displayed in table header */
  header: ReactNode
  /** Value accessor or custom cell renderer */
  accessor?: (row: T) => ReactNode
  /** Align text: 'left', 'center', or 'right' */
  align?: Alignment
  /** Specific CSS width (e.g. '150px', '20%') */
  width?: string
  /** Enable column click-to-sort */
  sortable?: boolean
  /** Value extractor for sorting (defaults to row[key]) */
  sortValue?: (row: T) => string | number | boolean | null | undefined
  /** Freeze column to the left on horizontal scroll */
  sticky?: boolean
  /** Cell CSS class name */
  className?: string
}

export interface DataTableProps<T> {
  /** Column definitions */
  columns: DataTableColumn<T>[]
  /** Array of row data items */
  data: T[]
  /** Function returning a unique ID for each row */
  getRowId: (row: T) => string | number
  /** Optional table title displayed in table header bar */
  title?: ReactNode
  /** Loading state indicator */
  isLoading?: boolean
  /** Skeleton row count during loading (default 5) */
  loadingRows?: number
  /** Empty state message or custom node */
  emptyText?: ReactNode
  /** Row click callback */
  onRowClick?: (row: T) => void
  /** Currently selected/active row ID */
  activeRowId?: string | number
  /** Number of items per page (0 or undefined turns off pagination) */
  pageSize?: number
  /** Available page size selection options (e.g. [10, 25, 50]) */
  pageSizeOptions?: number[]
  /** Initial density layout ('compact' or 'comfortable') */
  defaultDensity?: Density
  /** Enable or disable density toggle control */
  showDensityToggle?: boolean
  /** Additional controls rendered in header right area */
  headerControls?: ReactNode
  /** Custom table container CSS class */
  className?: string
}

function getColumnSortValue<T>(column: DataTableColumn<T>, row: T) {
  if (column.sortValue) return column.sortValue(row)
  const rawValue = (row as Record<string, unknown>)[column.key]
  if (
    typeof rawValue === 'string' ||
    typeof rawValue === 'number' ||
    typeof rawValue === 'boolean' ||
    rawValue == null
  ) {
    return rawValue
  }
  return column.accessor?.(row)
}

export function DataTable<T>({
  columns,
  data,
  getRowId,
  title,
  isLoading = false,
  loadingRows = 5,
  emptyText = 'No data available',
  onRowClick,
  activeRowId,
  pageSize: initialPageSize = 10,
  pageSizeOptions = [10, 25, 50, 100],
  defaultDensity = 'compact',
  showDensityToggle = true,
  headerControls,
  className = '',
}: DataTableProps<T>) {
  const [density, setDensity] = useState<Density>(defaultDensity)
  const [currentPage, setCurrentPage] = useState<number>(1)
  const [pageSize, setPageSize] = useState<number>(initialPageSize)
  const [sortKey, setSortKey] = useState<string | null>(null)
  const [sortDirection, setSortDirection] = useState<SortDirection>(null)

  // Handling Sort toggle
  const handleSort = (column: DataTableColumn<T>) => {
    if (!column.sortable) return

    if (sortKey !== column.key) {
      setSortKey(column.key)
      setSortDirection('asc')
    } else if (sortDirection === 'asc') {
      setSortDirection('desc')
    } else if (sortDirection === 'desc') {
      setSortKey(null)
      setSortDirection(null)
    } else {
      setSortDirection('asc')
    }
  }

  // Sorted data calculation
  const sortedData = useMemo(() => {
    if (!sortKey || !sortDirection) return data

    const column = columns.find((col) => col.key === sortKey)
    if (!column) return data

    return [...data].sort((a, b) => {
      const valA = getColumnSortValue(column, a)
      const valB = getColumnSortValue(column, b)

      if (valA === valB) return 0
      if (valA === null || valA === undefined) return 1
      if (valB === null || valB === undefined) return -1

      if (typeof valA === 'number' && typeof valB === 'number') {
        return sortDirection === 'asc' ? valA - valB : valB - valA
      }

      const strA = String(valA).toLowerCase()
      const strB = String(valB).toLowerCase()
      const cmp = strA.localeCompare(strB)
      return sortDirection === 'asc' ? cmp : -cmp
    })
  }, [data, columns, sortKey, sortDirection])

  // Pagination calculation
  const totalItems = sortedData.length
  const totalPages = pageSize > 0 ? Math.max(1, Math.ceil(totalItems / pageSize)) : 1
  const activePage = Math.min(currentPage, totalPages)

  const paginatedData = useMemo(() => {
    if (pageSize <= 0) return sortedData
    const start = (activePage - 1) * pageSize
    return sortedData.slice(start, start + pageSize)
  }, [sortedData, activePage, pageSize])

  const startRecord = (activePage - 1) * pageSize + 1
  const endRecord = Math.min(activePage * pageSize, totalItems)

  return (
    <div className={`nx-data-table-card ${className}`}>
      {/* Header bar (only rendered if title, controls, or density toggle enabled) */}
      {(title || headerControls || showDensityToggle) && (
        <div className="nx-data-table-header">
          <div className="nx-data-table-title">
            {title}
            <span className="nx-data-table-badge">{totalItems.toLocaleString()} items</span>
          </div>

          <div className="nx-data-table-controls">
            {headerControls}

            {showDensityToggle && (
              <button
                type="button"
                className={`nx-data-table-btn ${density === 'compact' ? 'is-active' : ''}`}
                onClick={() => setDensity((d) => (d === 'compact' ? 'comfortable' : 'compact'))}
                title="Toggle density layout"
              >
                <i className={`bi ${density === 'compact' ? 'bi-view-list' : 'bi-distribute-vertical'}`} aria-hidden="true" />
                <span>{density === 'compact' ? 'Compact' : 'Comfortable'}</span>
              </button>
            )}
          </div>
        </div>
      )}

      {/* Table responsive scroll area */}
      <div className="nx-data-table-container">
        <table className={`nx-data-table nx-data-table--${density}`}>
          <thead>
            <tr>
              {columns.map((column) => {
                const isSorted = sortKey === column.key
                const alignClass = column.align ? `text-${column.align}` : ''
                const stickyClass = column.sticky ? 'is-sticky-left' : ''
                const sortableClass = column.sortable ? 'is-sortable' : ''

                return (
                  <th
                    key={column.key}
                    style={{ width: column.width }}
                    className={`${alignClass} ${stickyClass} ${sortableClass} ${column.className ?? ''}`.trim()}
                    onClick={() => handleSort(column)}
                    onKeyDown={(event) => {
                      if (!column.sortable || (event.key !== 'Enter' && event.key !== ' ')) return
                      event.preventDefault()
                      handleSort(column)
                    }}
                    tabIndex={column.sortable ? 0 : undefined}
                    aria-sort={
                      isSorted
                        ? sortDirection === 'asc'
                          ? 'ascending'
                          : 'descending'
                        : column.sortable
                          ? 'none'
                          : undefined
                    }
                  >
                    <div style={{ display: 'inline-flex', alignItems: 'center', justifyContent: column.align === 'right' ? 'flex-end' : column.align === 'center' ? 'center' : 'flex-start' }}>
                      {column.header}
                      {column.sortable && (
                        <span className={`nx-data-table-sort-icon ${isSorted ? 'is-active' : ''}`}>
                          {isSorted && sortDirection === 'asc' && <i className="bi bi-sort-alpha-down" />}
                          {isSorted && sortDirection === 'desc' && <i className="bi bi-sort-alpha-up-alt" />}
                          {!isSorted && <i className="bi bi-arrow-down-up" />}
                        </span>
                      )}
                    </div>
                  </th>
                )
              })}
            </tr>
          </thead>

          <tbody>
            {isLoading ? (
              Array.from({ length: loadingRows }).map((_, index) => (
                <tr key={`loading-${index}`} className="nx-data-table-skeleton-row">
                  {columns.map((column) => (
                    <td key={column.key}>
                      <div style={{ height: '16px', background: 'var(--nx-rule, #cbd5e1)', borderRadius: '4px', opacity: 0.4 }} />
                    </td>
                  ))}
                </tr>
              ))
            ) : paginatedData.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="nx-data-table-empty">
                  <div className="text-secondary py-3">
                    <i className="bi bi-inbox fs-3 d-block mb-2 text-muted" aria-hidden="true" />
                    <div>{emptyText}</div>
                  </div>
                </td>
              </tr>
            ) : (
              paginatedData.map((row) => {
                const rowId = getRowId(row)
                const isSelected = rowId === activeRowId

                return (
                  <tr
                    key={rowId}
                    className={`nx-data-table-row ${onRowClick ? 'is-clickable' : ''} ${isSelected ? 'is-selected' : ''}`}
                    onClick={() => onRowClick?.(row)}
                    onKeyDown={(event) => {
                      if (!onRowClick || (event.key !== 'Enter' && event.key !== ' ')) return
                      event.preventDefault()
                      onRowClick(row)
                    }}
                    tabIndex={onRowClick ? 0 : undefined}
                  >
                    {columns.map((column) => {
                      const alignClass = column.align ? `text-${column.align}` : ''
                      const stickyClass = column.sticky ? 'is-sticky-left' : ''

                      let cellContent: ReactNode
                      if (column.accessor) {
                        cellContent = column.accessor(row)
                      } else {
                        cellContent = String((row as Record<string, unknown>)[column.key] ?? '—')
                      }

                      return (
                        <td
                          key={column.key}
                          className={`${alignClass} ${stickyClass} ${column.className ?? ''}`.trim()}
                        >
                          {cellContent}
                        </td>
                      )
                    })}
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Footer */}
      {!isLoading && pageSize > 0 && totalItems > 0 && (
        <div className="nx-data-table-footer">
          <div className="nx-data-table-pagination-info">
            <span>
              Showing {startRecord}–{endRecord} of {totalItems}
            </span>

            {pageSizeOptions.length > 0 && (
              <label style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', margin: 0 }}>
                <span>Rows per page:</span>
                <select
                  className="nx-data-table-page-size-select"
                  aria-label="Rows per page"
                  value={pageSize}
                  onChange={(e) => {
                    setPageSize(Number(e.target.value))
                    setCurrentPage(1)
                  }}
                >
                  {pageSizeOptions.map((opt) => (
                    <option key={opt} value={opt}>
                      {opt}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>

          {totalPages > 1 && (
            <div className="nx-data-table-pagination-nav">
              <button
                type="button"
                className="nx-data-table-page-btn"
                disabled={activePage === 1}
                onClick={() => setCurrentPage(1)}
                title="First Page"
              >
                <i className="bi bi-chevron-double-left" />
              </button>

              <button
                type="button"
                className="nx-data-table-page-btn"
                disabled={activePage === 1}
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                title="Previous Page"
              >
                <i className="bi bi-chevron-left" />
              </button>

              {Array.from({ length: totalPages }).map((_, i) => {
                const pageNum = i + 1
                // Show current, first, last, and adjacent pages
                if (
                  pageNum === 1 ||
                  pageNum === totalPages ||
                  Math.abs(pageNum - activePage) <= 1
                ) {
                  return (
                    <button
                      key={pageNum}
                      type="button"
                      className={`nx-data-table-page-btn ${pageNum === activePage ? 'is-active' : ''}`}
                      onClick={() => setCurrentPage(pageNum)}
                    >
                      {pageNum}
                    </button>
                  )
                }
                if (
                  (pageNum === 2 && activePage > 3) ||
                  (pageNum === totalPages - 1 && activePage < totalPages - 2)
                ) {
                  return <span key={pageNum} style={{ padding: '0 0.2rem', opacity: 0.5 }}>...</span>
                }
                return null
              })}

              <button
                type="button"
                className="nx-data-table-page-btn"
                disabled={activePage === totalPages}
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                title="Next Page"
              >
                <i className="bi bi-chevron-right" />
              </button>

              <button
                type="button"
                className="nx-data-table-page-btn"
                disabled={activePage === totalPages}
                onClick={() => setCurrentPage(totalPages)}
                title="Last Page"
              >
                <i className="bi bi-chevron-double-right" />
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
