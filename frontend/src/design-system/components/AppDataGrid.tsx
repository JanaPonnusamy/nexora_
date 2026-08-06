import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { EmptyState } from '../../components/common/EmptyState'

type GridDensity = 'compact' | 'comfortable'

export interface AppDataGridColumn<T> {
  key: string
  header: string
  render?: (row: T) => ReactNode
  align?: 'start' | 'end' | 'center'
  width?: string
  sticky?: boolean
  defaultVisible?: boolean
}

interface AppDataGridProps<T> {
  title?: string
  storageKey?: string
  columns: AppDataGridColumn<T>[]
  rows: T[]
  getRowId: (row: T) => string
  isLoading?: boolean
  emptyTitle?: string
  emptyDescription?: string
  onRowClick?: (row: T) => void
  activeRowId?: string
  pageSize?: number
  actions?: ReactNode
}

function loadGridPref(storageKey: string, fallback: Record<string, boolean>) {
  try {
    const raw = localStorage.getItem(storageKey)
    if (!raw) return fallback
    return { ...fallback, ...(JSON.parse(raw) as Record<string, boolean>) }
  } catch {
    return fallback
  }
}

export function AppDataGrid<T>({
  title,
  storageKey,
  columns,
  rows,
  getRowId,
  isLoading = false,
  emptyTitle = 'No data',
  emptyDescription,
  onRowClick,
  activeRowId,
  pageSize = 0,
  actions,
}: AppDataGridProps<T>) {
  const visibilityDefault = useMemo(
    () => Object.fromEntries(columns.map((column) => [column.key, column.defaultVisible !== false])),
    [columns],
  )
  const [density, setDensity] = useState<GridDensity>('compact')
  const [page, setPage] = useState(0)
  const [columnVisibility, setColumnVisibility] = useState<Record<string, boolean>>(
    storageKey ? loadGridPref(`${storageKey}:visibility`, visibilityDefault) : visibilityDefault,
  )

  useEffect(() => {
    if (!storageKey) return
    localStorage.setItem(`${storageKey}:visibility`, JSON.stringify(columnVisibility))
  }, [storageKey, columnVisibility])

  const visibleColumns = columns.filter((column) => columnVisibility[column.key] !== false)
  const totalPages = pageSize > 0 ? Math.max(1, Math.ceil(rows.length / pageSize)) : 1
  const safePage = Math.min(page, totalPages - 1)
  const pagedRows =
    pageSize > 0 ? rows.slice(safePage * pageSize, safePage * pageSize + pageSize) : rows

  function exportCsv() {
    const header = visibleColumns.map((column) => column.header)
    const body = rows.map((row) =>
      visibleColumns.map((column) => {
        const value = column.render ? column.render(row) : (row as Record<string, unknown>)[column.key]
        const text = typeof value === 'string' || typeof value === 'number' ? String(value) : ''
        return `"${text.replaceAll('"', '""')}"`
      }).join(','))
    const csv = [header.join(','), ...body].join('\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `${storageKey ?? 'grid-export'}.csv`
    anchor.click()
    URL.revokeObjectURL(url)
  }

  return (
    <section className="ds-grid-card">
      <div className="ds-grid-card__toolbar">
        <div className="ds-grid-card__title">
          {title && <h3>{title}</h3>}
          {pageSize > 0 && <span>{rows.length.toLocaleString()} rows</span>}
        </div>
        <div className="ds-grid-card__actions">
          <div className="ds-grid-card__density" role="group" aria-label="Grid density">
            <button type="button" className={density === 'compact' ? 'is-active' : ''} onClick={() => setDensity('compact')}>Compact</button>
            <button type="button" className={density === 'comfortable' ? 'is-active' : ''} onClick={() => setDensity('comfortable')}>Comfortable</button>
          </div>
          <details className="ds-grid-card__columns">
            <summary>Columns</summary>
            <div className="ds-grid-card__column-list">
              {columns.map((column) => (
                <label key={column.key}>
                  <input
                    type="checkbox"
                    checked={columnVisibility[column.key] !== false}
                    onChange={(event) =>
                      setColumnVisibility((current) => ({ ...current, [column.key]: event.target.checked }))}
                  />
                  {column.header}
                </label>
              ))}
            </div>
          </details>
          <button type="button" className="btn btn-outline-secondary ds-button" onClick={exportCsv}>
            <i className="bi bi-download me-1" aria-hidden="true" />
            Export
          </button>
          {actions}
        </div>
      </div>

      <div className={`ds-grid-card__tablewrap ds-grid-card__tablewrap--${density}`}>
        <table className="ds-data-grid">
          <thead>
            <tr>
              {visibleColumns.map((column) => (
                <th
                  key={column.key}
                  style={{ width: column.width, textAlign: column.align }}
                  className={column.sticky ? 'is-sticky' : ''}
                >
                  {column.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pagedRows.map((row) => {
              const rowId = getRowId(row)
              return (
                <tr
                  key={rowId}
                  tabIndex={onRowClick ? 0 : -1}
                  className={[
                    onRowClick ? 'is-clickable' : '',
                    rowId === activeRowId ? 'is-active' : '',
                  ].filter(Boolean).join(' ')}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                >
                  {visibleColumns.map((column) => (
                    <td
                      key={column.key}
                      style={{ textAlign: column.align }}
                      className={column.sticky ? 'is-sticky' : ''}
                    >
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

        {isLoading && <div className="ds-grid-card__loading">Loading data...</div>}
        {!isLoading && rows.length === 0 && (
          <div className="ds-grid-card__empty">
            <EmptyState icon="bi-table" title={emptyTitle} description={emptyDescription} />
          </div>
        )}
      </div>

      {pageSize > 0 && totalPages > 1 && (
        <div className="ds-grid-card__pager">
          <span>Page {safePage + 1} of {totalPages}</span>
          <div>
            <button type="button" disabled={safePage === 0} onClick={() => setPage((current) => Math.max(0, current - 1))}>Previous</button>
            <button type="button" disabled={safePage >= totalPages - 1} onClick={() => setPage((current) => Math.min(totalPages - 1, current + 1))}>Next</button>
          </div>
        </div>
      )}
    </section>
  )
}
