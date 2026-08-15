import { useEffect, useMemo, useState } from 'react'
import { useAsyncData } from '../../hooks/useAsyncData'
import { syncService } from '../../services/syncService'
import { TableSkeleton } from '../common/TableSkeleton'
import { ErrorState } from '../common/ErrorState'
import { ToggleCheck } from '../dashboard/ToggleCheck'
import type { TableColumn, SyncTable } from '../../types/sync'
import {
  SxCard, SxCardHead, SxCardBody, SxStat, SxButton,
} from './ui'

type ToggleField = 'is_selected' | 'is_pk' | 'is_hash'
type FilterType = 'all' | 'mapped' | 'unmapped' | 'pk' | 'hash'

function getDataTypeBadge(dtype: string) {
  const d = (dtype || '').toLowerCase()
  let toneClass = 'sx-dtype--default'
  if (d.includes('int') || d.includes('num') || d.includes('dec') || d.includes('float') || d.includes('double') || d.includes('real')) {
    toneClass = 'sx-dtype--number'
  } else if (d.includes('char') || d.includes('text') || d.includes('str') || d.includes('uuid')) {
    toneClass = 'sx-dtype--string'
  } else if (d.includes('date') || d.includes('time')) {
    toneClass = 'sx-dtype--date'
  } else if (d.includes('bool')) {
    toneClass = 'sx-dtype--bool'
  } else if (d.includes('json') || d.includes('blob') || d.includes('byte')) {
    toneClass = 'sx-dtype--json'
  }
  return <span className={`sx-dtype ${toneClass}`}>{dtype || 'unknown'}</span>
}

export function ColumnMappingTab() {
  const { data: tables, isLoading: tablesLoading, error: tablesError, reload: reloadTables } = useAsyncData(syncService.tables)
  const [tableSearch, setTableSearch] = useState('')
  const [columnSearch, setColumnSearch] = useState('')
  const [columnFilter, setColumnFilter] = useState<FilterType>('all')
  const [selectedId, setSelectedId] = useState('')
  const [tableName, setTableName] = useState('')
  const [columns, setColumns] = useState<TableColumn[]>([])
  const [columnsLoading, setColumnsLoading] = useState(false)
  const [columnsError, setColumnsError] = useState<string | null>(null)
  const [saving, setSaving] = useState<Set<string>>(new Set())
  const [bulkBusy, setBulkBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [toastMessage, setToastMessage] = useState<string | null>(null)

  // Auto-dismiss toast
  useEffect(() => {
    if (!toastMessage) return
    const timer = setTimeout(() => setToastMessage(null), 3500)
    return () => clearTimeout(timer)
  }, [toastMessage])

  const filteredTables = useMemo(() => {
    const query = tableSearch.trim().toLowerCase()
    const list = tables ?? []
    if (!query) return list
    return list.filter((table) => table.table_name.toLowerCase().includes(query))
  }, [tables, tableSearch])

  const activeTable = useMemo<SyncTable | undefined>(() => {
    return tables?.find((t) => t.sync_table_id === selectedId)
  }, [tables, selectedId])

  useEffect(() => {
    if (filteredTables.length > 0 && !filteredTables.some((t) => t.sync_table_id === selectedId)) {
      setSelectedId(filteredTables[0].sync_table_id)
    }
  }, [filteredTables, selectedId])

  const fetchColumns = (id: string) => {
    if (!id) return
    let active = true
    setColumnsLoading(true)
    setColumnsError(null)
    syncService.tableColumns(id)
      .then((result) => {
        if (!active) return
        setTableName(result.table_name)
        setColumns(result.columns || [])
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
  }

  useEffect(() => {
    return fetchColumns(selectedId)
  }, [selectedId])

  const stats = useMemo(() => {
    const total = columns.length
    const mapped = columns.filter((c) => c.is_selected).length
    const pk = columns.filter((c) => c.is_pk).length
    const hash = columns.filter((c) => c.is_hash).length
    const pct = total > 0 ? Math.round((mapped / total) * 100) : 0
    return { total, mapped, pk, hash, pct }
  }, [columns])

  const visibleColumns = useMemo(() => {
    const query = columnSearch.trim().toLowerCase()
    return columns.filter((column) => {
      if (query && !column.column_name.toLowerCase().includes(query) && !column.data_type.toLowerCase().includes(query)) {
        return false
      }
      if (columnFilter === 'mapped') return column.is_selected
      if (columnFilter === 'unmapped') return !column.is_selected
      if (columnFilter === 'pk') return column.is_pk
      if (columnFilter === 'hash') return column.is_hash
      return true
    })
  }, [columns, columnSearch, columnFilter])

  const toggle = async (column: TableColumn, field: ToggleField) => {
    if (saving.has(column.column_name) || bulkBusy) return
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

  const handleBulkSelect = async (selectAll: boolean) => {
    if (bulkBusy || columns.length === 0) return
    setBulkBusy(true)
    setActionError(null)
    const targetCols = columns.filter((c) => c.is_selected !== selectAll)
    if (targetCols.length === 0) {
      setBulkBusy(false)
      return
    }

    setColumns((prev) => prev.map((c) => ({ ...c, is_selected: selectAll })))

    try {
      await Promise.all(
        targetCols.map((col) =>
          syncService.saveMapping({
            sync_table_id: selectedId,
            table_name: tableName,
            column_name: col.column_name,
            data_type: col.data_type,
            is_selected: selectAll,
            is_pk: col.is_pk,
            is_hash: col.is_hash,
            is_watermark: col.is_watermark,
            column_order: col.column_order,
          })
        )
      )
      setToastMessage(selectAll ? `All ${columns.length} columns mapped successfully` : 'All columns unmapped')
    } catch (err) {
      fetchColumns(selectedId)
      setActionError(err instanceof Error ? err.message : 'Failed to update all mappings')
    } finally {
      setBulkBusy(false)
    }
  }

  if (tablesLoading) return <TableSkeleton rows={6} columns={6} />
  if (tablesError || !tables) return <ErrorState description={tablesError ?? 'Failed to load tables'} onRetry={reloadTables} />
  if (tables.length === 0) {
    return (
      <div className="sx-mapping__empty">
        <div className="sx-mapping__empty-icon"><i className="bi bi-diagram-3" /></div>
        <h4 className="sx-mapping__empty-title">No Configured Sync Tables</h4>
        <p className="sx-mapping__empty-desc">Configure a sync table first from the sync configuration tab, then manage column mappings here.</p>
      </div>
    )
  }

  return (
    <div className="sx-stack sx-mapping">
      {/* Top Stat Overview */}
      <div className="row row-cols-2 row-cols-md-4 g-2">
        <div className="col">
          <SxStat
            icon="bi-layout-three-columns"
            tone="indigo"
            value={stats.total}
            label="Total Columns"
            sub="In selected table"
          />
        </div>
        <div className="col">
          <SxStat
            icon="bi-check2-circle"
            tone="success"
            value={stats.mapped}
            label="Mapped Columns"
            sub={`${stats.pct}% coverage`}
          />
        </div>
        <div className="col">
          <SxStat
            icon="bi-key-fill"
            tone="warning"
            value={stats.pk}
            label="Primary Keys"
            sub={stats.pk === 1 ? '1 PK designated' : `${stats.pk} PKs designated`}
          />
        </div>
        <div className="col">
          <SxStat
            icon="bi-hash"
            tone="info"
            value={stats.hash}
            label="Hash Columns"
            sub={`${stats.hash} change-track columns`}
          />
        </div>
      </div>

      {/* Main Split View */}
      <div className="sx-mapping__split">
        {/* Left Tables Sidebar */}
        <SxCard className="sx-pane sx-mapping__nav">
          <SxCardHead
            title="Sync Tables"
            icon="bi-table"
            sub={`${filteredTables.length} of ${tables.length} tables`}
          />
          <SxCardBody flush>
            <div className="sx-mapping__search">
              <div className="ds-filter-search position-relative w-100">
                <i className="bi bi-search" aria-hidden="true" />
                <input
                  type="search"
                  value={tableSearch}
                  onChange={(e) => setTableSearch(e.target.value)}
                  placeholder="Filter tables..."
                  aria-label="Filter sync tables"
                />
                {tableSearch && (
                  <button
                    type="button"
                    className="btn btn-sm text-muted position-absolute end-0 top-50 translate-middle-y me-1 p-0 border-0 bg-transparent"
                    onClick={() => setTableSearch('')}
                    aria-label="Clear table search"
                  >
                    <i className="bi bi-x-circle-fill" />
                  </button>
                )}
              </div>
            </div>

            <div className="sx-mapping__table-list">
              {filteredTables.map((table) => {
                const isSelected = table.sync_table_id === selectedId
                return (
                  <button
                    key={table.sync_table_id}
                    type="button"
                    className={`sx-list__item${isSelected ? ' sx-list__item--active' : ''}`}
                    title={table.table_name}
                    onClick={() => setSelectedId(table.sync_table_id)}
                  >
                    <span className="d-flex align-items-center gap-2 min-w-0">
                      <i className={`bi ${isSelected ? 'bi-table text-primary' : 'bi-table text-muted'}`} />
                      <span className="sx-mapping__table-name">{table.table_name}</span>
                    </span>
                    <span className="sx-mapping__table-meta">
                      <span className="sx-mapping__tag">
                        {table.sync_mode ? table.sync_mode.substring(0, 3) : 'INC'}
                      </span>
                      {table.is_active ? (
                        <i className="bi bi-check-circle-fill sx-mapping__table-state" title="Sync Active" aria-hidden="true" />
                      ) : (
                        <i className="bi bi-dash-circle sx-mapping__table-state--dim" title="Sync Inactive" aria-hidden="true" />
                      )}
                    </span>
                  </button>
                )
              })}
              {filteredTables.length === 0 && (
                <div className="text-center py-4 px-2 text-muted small">
                  <i className="bi bi-search d-block mb-1 fs-5 opacity-50" />
                  No tables match &quot;{tableSearch}&quot;
                  <button
                    type="button"
                    className="btn btn-link btn-sm d-block mx-auto mt-1 p-0"
                    onClick={() => setTableSearch('')}
                  >
                    Clear filter
                  </button>
                </div>
              )}
            </div>
          </SxCardBody>
        </SxCard>

        {/* Right Columns Mapping Panel */}
        <SxCard className="sx-pane sx-mapping__main">
          <SxCardHead
            title={tableName || activeTable?.table_name || 'Table Columns'}
            icon="bi-diagram-3"
            sub={
              <div className="d-flex align-items-center gap-2 flex-wrap">
                <span className="badge bg-secondary-subtle text-secondary border">
                  {activeTable?.sync_mode ?? 'INCREMENTAL'}
                </span>
                <span className={`badge ${activeTable?.is_active ? 'bg-success-subtle text-success' : 'bg-secondary-subtle text-secondary'} border`}>
                  {activeTable?.is_active ? 'Active' : 'Inactive'}
                </span>
                <span className="badge bg-primary-subtle text-primary border">
                  {stats.mapped} of {stats.total} Mapped ({stats.pct}%)
                </span>
              </div>
            }
            action={
              <div className="sx-mapping__header-actions">
                {columns.length > 0 && (
                  <>
                    <SxButton
                      sm
                      variant="ghost"
                      icon="bi-check-all"
                      busy={bulkBusy}
                      onClick={() => handleBulkSelect(true)}
                      title="Map all columns"
                    >
                      Map All
                    </SxButton>
                    <SxButton
                      sm
                      variant="ghost"
                      icon="bi-x-lg"
                      busy={bulkBusy}
                      onClick={() => handleBulkSelect(false)}
                      title="Unmap all columns"
                    >
                      Unmap All
                    </SxButton>
                  </>
                )}
                <SxButton
                  sm
                  variant="ghost"
                  icon="bi-arrow-clockwise"
                  busy={columnsLoading}
                  onClick={() => fetchColumns(selectedId)}
                  title="Reload columns"
                />
              </div>
            }
          />

          {/* Column Filter Bar */}
          {columns.length > 0 && (
            <div className="sx-mapping__filter-bar">
              <div className="sx-mapping__filter-chips">
                <button
                  type="button"
                  className={`sx-mapping__chip-btn${columnFilter === 'all' ? ' sx-mapping__chip-btn--active' : ''}`}
                  onClick={() => setColumnFilter('all')}
                >
                  All ({columns.length})
                </button>
                <button
                  type="button"
                  className={`sx-mapping__chip-btn${columnFilter === 'mapped' ? ' sx-mapping__chip-btn--active' : ''}`}
                  onClick={() => setColumnFilter('mapped')}
                >
                  Mapped ({stats.mapped})
                </button>
                <button
                  type="button"
                  className={`sx-mapping__chip-btn${columnFilter === 'unmapped' ? ' sx-mapping__chip-btn--active' : ''}`}
                  onClick={() => setColumnFilter('unmapped')}
                >
                  Unmapped ({stats.total - stats.mapped})
                </button>
                <button
                  type="button"
                  className={`sx-mapping__chip-btn${columnFilter === 'pk' ? ' sx-mapping__chip-btn--active' : ''}`}
                  onClick={() => setColumnFilter('pk')}
                >
                  PKs ({stats.pk})
                </button>
              </div>

              <div className="ds-filter-search" style={{ minWidth: '180px', maxWidth: '280px' }}>
                <i className="bi bi-search" aria-hidden="true" />
                <input
                  type="search"
                  value={columnSearch}
                  onChange={(e) => setColumnSearch(e.target.value)}
                  placeholder="Search columns or types..."
                  aria-label="Search columns"
                  style={{ minHeight: '30px', fontSize: '0.78rem' }}
                />
              </div>
            </div>
          )}

          <SxCardBody flush>
            {toastMessage && (
              <div className="p-3 pb-0">
                <div className="alert alert-success d-flex align-items-center gap-2 py-2 px-3 mb-0" role="alert">
                  <i className="bi bi-check-circle-fill fs-6" />
                  <span className="small">{toastMessage}</span>
                </div>
              </div>
            )}

            {actionError && (
              <div className="p-3 pb-0">
                <div className="alert alert-danger d-flex align-items-center gap-2 py-2 px-3 mb-0" role="alert">
                  <i className="bi bi-exclamation-triangle-fill fs-6" />
                  <span className="small">{actionError}</span>
                </div>
              </div>
            )}

            {columnsLoading ? (
              <div className="p-3">
                <TableSkeleton rows={8} columns={6} />
              </div>
            ) : columnsError ? (
              <div className="p-4">
                <ErrorState
                  description={columnsError}
                  onRetry={() => fetchColumns(selectedId)}
                />
              </div>
            ) : columns.length === 0 ? (
              <div className="sx-mapping__empty">
                <div className="sx-mapping__empty-icon">
                  <i className="bi bi-database-slash" />
                </div>
                <h4 className="sx-mapping__empty-title">No Catalog Columns Found</h4>
                <p className="sx-mapping__empty-desc">
                  Table <strong>{tableName || activeTable?.table_name}</strong> does not have discovered schema columns registered yet. Register the store schema or populate the table catalog to begin column mappings.
                </p>
                <div className="d-flex gap-2 mt-2">
                  <SxButton
                    variant="primary"
                    icon="bi-arrow-clockwise"
                    onClick={() => fetchColumns(selectedId)}
                  >
                    Refresh Schema
                  </SxButton>
                </div>
              </div>
            ) : visibleColumns.length === 0 ? (
              <div className="sx-mapping__empty">
                <div className="sx-mapping__empty-icon">
                  <i className="bi bi-search" />
                </div>
                <h4 className="sx-mapping__empty-title">No Matching Columns</h4>
                <p className="sx-mapping__empty-desc">
                  No columns match your current search query or filter selection.
                </p>
                <button
                  type="button"
                  className="btn btn-outline-secondary btn-sm mt-2"
                  onClick={() => {
                    setColumnSearch('')
                    setColumnFilter('all')
                  }}
                >
                  Clear Filters
                </button>
              </div>
            ) : (
              <div className="sx-mapping__tablewrap">
                <table className="sx-table">
                  <colgroup>
                    <col style={{ width: '64px' }} />
                    <col style={{ width: '28%' }} />
                    <col style={{ width: '28%' }} />
                    <col style={{ width: '120px' }} />
                    <col style={{ width: '120px' }} />
                    <col style={{ width: '64px' }} />
                    <col style={{ width: '64px' }} />
                  </colgroup>
                  <thead>
                    <tr>
                      <th className="text-center">Sync</th>
                      <th>Store Column (Source)</th>
                      <th>HO Column (Target)</th>
                      <th>Store Type</th>
                      <th>HO Type</th>
                      <th className="text-center">PK</th>
                      <th className="text-center">Hash</th>
                    </tr>
                  </thead>
                  <tbody className="sx-mapping__tbody">
                    {visibleColumns.map((column) => {
                      const isSaving = saving.has(column.column_name) || bulkBusy
                      return (
                        <tr
                          key={column.column_name}
                          className={`sx-mapping__row${!column.is_selected ? ' sx-mapping__row--unmapped' : ''}`}
                        >
                          <td className="text-center">
                            <ToggleCheck
                              checked={column.is_selected}
                              busy={isSaving}
                              label={`Toggle sync for ${column.column_name}`}
                              onClick={() => toggle(column, 'is_selected')}
                            />
                          </td>
                          <td>
                            <div className="d-flex align-items-center gap-2">
                              <i className={`bi ${column.is_selected ? 'bi-dot text-primary fs-5' : 'bi-dot text-muted fs-5'}`} />
                              <span
                                className={`sx-mapping__cellname ${column.is_selected ? 'text-emphasis font-monospace' : 'text-muted font-monospace'}`}
                                title={column.column_name}
                              >
                                {column.column_name}
                              </span>
                              {column.is_watermark && (
                                <span className="badge bg-info-subtle text-info border border-info-subtle small px-1 py-0">
                                  Watermark
                                </span>
                              )}
                            </div>
                          </td>
                          <td>
                            <span className="sx-mapping__cellname text-muted font-monospace" title={column.column_name}>
                              {column.column_name}
                            </span>
                          </td>
                          <td>{getDataTypeBadge(column.data_type)}</td>
                          <td>{getDataTypeBadge(column.data_type)}</td>
                          <td className="text-center">
                            <ToggleCheck
                              checked={column.is_pk}
                              busy={isSaving}
                              label={`Toggle primary key for ${column.column_name}`}
                              onClick={() => toggle(column, 'is_pk')}
                            />
                          </td>
                          <td className="text-center">
                            <ToggleCheck
                              checked={column.is_hash}
                              busy={isSaving}
                              label={`Toggle hash for ${column.column_name}`}
                              onClick={() => toggle(column, 'is_hash')}
                            />
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </SxCardBody>
        </SxCard>
      </div>
    </div>
  )
}

