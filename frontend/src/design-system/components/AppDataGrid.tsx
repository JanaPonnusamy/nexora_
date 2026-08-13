import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { DataTable, type DataTableColumn } from '../../components/common/DataTable'

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
  const [columnVisibility, setColumnVisibility] = useState<Record<string, boolean>>(
    storageKey ? loadGridPref(`${storageKey}:visibility`, visibilityDefault) : visibilityDefault,
  )

  useEffect(() => {
    if (!storageKey) return
    localStorage.setItem(`${storageKey}:visibility`, JSON.stringify(columnVisibility))
  }, [storageKey, columnVisibility])

  const visibleColumns = columns.filter((column) => columnVisibility[column.key] !== false)

  const dataTableColumns: DataTableColumn<T>[] = visibleColumns.map((column) => ({
    key: column.key,
    header: column.header,
    accessor: column.render,
    align:
      column.align === 'start' ? 'left' : column.align === 'end' ? 'right' : column.align,
    width: column.width,
    sticky: column.sticky,
    sortable: true,
  }))

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

  const controls = (
    <>
      <details className="ds-grid-card__columns">
        <summary className="nx-data-table-btn">Columns</summary>
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
      <button type="button" className="nx-data-table-btn" onClick={exportCsv}>
        <i className="bi bi-download" aria-hidden="true" />
        Export
      </button>
      {actions}
    </>
  )

  return (
    <DataTable
      title={title}
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
      pageSize={pageSize}
      headerControls={controls}
    />
  )
}
