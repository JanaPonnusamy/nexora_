import { useEffect, useState } from 'react'
import { useAsyncData } from '../../hooks/useAsyncData'
import { syncService } from '../../services/syncService'
import { EmptyState } from '../common/EmptyState'
import { ErrorState } from '../common/ErrorState'
import { TableSkeleton } from '../common/TableSkeleton'
import type { TableColumn } from '../../types/sync'

type ToggleField = 'is_selected' | 'is_pk' | 'is_hash'

export function ColumnMappingTab() {
  const { data: tables, isLoading: tablesLoading, error: tablesError, reload } = useAsyncData(syncService.tables)
  const [selectedId, setSelectedId] = useState('')
  const [tableName, setTableName] = useState('')
  const [columns, setColumns] = useState<TableColumn[]>([])
  const [columnsLoading, setColumnsLoading] = useState(false)
  const [columnsError, setColumnsError] = useState<string | null>(null)
  const [saving, setSaving] = useState<Set<string>>(new Set())
  const [actionError, setActionError] = useState<string | null>(null)

  useEffect(() => {
    if (tables && tables.length > 0 && !selectedId) {
      setSelectedId(tables[0].sync_table_id)
    }
  }, [tables, selectedId])

  useEffect(() => {
    if (!selectedId) return
    let active = true
    setColumnsLoading(true)
    setColumnsError(null)
    syncService
      .tableColumns(selectedId)
      .then((result) => {
        if (!active) return
        setTableName(result.table_name)
        setColumns(result.columns)
      })
      .catch((err) => {
        if (!active) return
        setColumnsError(err instanceof Error ? err.message : 'Failed to load columns')
      })
      .finally(() => {
        if (active) setColumnsLoading(false)
      })
    return () => {
      active = false
    }
  }, [selectedId])

  const toggle = async (column: TableColumn, field: ToggleField) => {
    if (saving.has(column.column_name)) return
    const updated: TableColumn = { ...column, [field]: !column[field] }
    setColumns((prev) => prev.map((c) => (c.column_name === column.column_name ? updated : c)))
    setSaving((prev) => new Set(prev).add(column.column_name))
    setActionError(null)
    try {
      await syncService.saveMapping({
        sync_table_id: selectedId,
        table_name: tableName,
        column_name: updated.column_name,
        data_type: updated.data_type,
        is_selected: updated.is_selected,
        is_pk: updated.is_pk,
        is_hash: updated.is_hash,
        is_watermark: updated.is_watermark,
        column_order: updated.column_order,
      })
    } catch (err) {
      setColumns((prev) => prev.map((c) => (c.column_name === column.column_name ? column : c)))
      setActionError(err instanceof Error ? err.message : 'Failed to save mapping')
    } finally {
      setSaving((prev) => {
        const next = new Set(prev)
        next.delete(column.column_name)
        return next
      })
    }
  }

  const toggleButton = (column: TableColumn, field: ToggleField, label: string) => {
    const on = column[field]
    return (
      <button
        type="button"
        className={`btn btn-sm permission-cell ${on ? 'btn-success' : 'btn-outline-secondary'}`}
        aria-pressed={on}
        aria-label={`${on ? 'Disable' : 'Enable'} ${label} for ${column.column_name}`}
        disabled={saving.has(column.column_name)}
        onClick={() => toggle(column, field)}
      >
        {saving.has(column.column_name) ? (
          <span className="spinner-border spinner-border-sm" aria-hidden="true" />
        ) : (
          <i className={`bi ${on ? 'bi-check-lg' : 'bi-x-lg'}`} aria-hidden="true" />
        )}
      </button>
    )
  }

  if (tablesLoading) return <TableSkeleton rows={5} columns={6} />
  if (tablesError || !tables) return <ErrorState description={tablesError ?? 'Failed to load tables'} onRetry={reload} />
  if (tables.length === 0) {
    return (
      <EmptyState
        icon="bi-diagram-3"
        title="No configured tables"
        description="Configure a sync table first, then map its columns here."
      />
    )
  }

  return (
    <div>
      <div className="mb-3 col-md-5 col-lg-4">
        <label htmlFor="mapping-table" className="form-label">Configured Table</label>
        <select
          id="mapping-table"
          className="form-select"
          value={selectedId}
          onChange={(e) => setSelectedId(e.target.value)}
        >
          {tables.map((table) => (
            <option key={table.sync_table_id} value={table.sync_table_id}>
              {table.table_name}
            </option>
          ))}
        </select>
      </div>

      {actionError && <div className="alert alert-danger py-2">{actionError}</div>}

      {columnsLoading ? (
        <TableSkeleton rows={5} columns={6} />
      ) : columnsError ? (
        <ErrorState description={columnsError} onRetry={() => setSelectedId(selectedId)} />
      ) : columns.length === 0 ? (
        <EmptyState
          icon="bi-diagram-3"
          title="No catalog columns"
          description="No discovered columns for this table yet. Register the store schema to populate the catalog."
        />
      ) : (
        <div className="table-responsive">
          <table className="table table-hover align-middle data-table">
            <thead>
              <tr>
                <th scope="col">Enabled</th>
                <th scope="col">Store Column</th>
                <th scope="col">HO Column</th>
                <th scope="col">Store Type</th>
                <th scope="col">HO Type</th>
                <th scope="col">PK</th>
                <th scope="col">Hash</th>
              </tr>
            </thead>
            <tbody>
              {columns.map((column) => (
                <tr key={column.column_name}>
                  <td>{toggleButton(column, 'is_selected', 'sync')}</td>
                  <td className="fw-medium">{column.column_name}</td>
                  <td>{column.column_name}</td>
                  <td className="text-secondary">{column.data_type}</td>
                  <td className="text-secondary">{column.data_type}</td>
                  <td>{toggleButton(column, 'is_pk', 'primary key')}</td>
                  <td>{toggleButton(column, 'is_hash', 'hash')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
