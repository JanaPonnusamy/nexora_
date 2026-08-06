import { useEffect, useMemo, useState } from 'react'
import { useAsyncData } from '../../hooks/useAsyncData'
import { syncService } from '../../services/syncService'
import { EmptyState } from '../common/EmptyState'
import { ErrorState } from '../common/ErrorState'
import { TableSkeleton } from '../common/TableSkeleton'
import { ToggleCheck } from '../dashboard/ToggleCheck'
import type { TableColumn } from '../../types/sync'
import {
  SxCard, SxCardHead, SxCardBody, SxStat, SxSearch, SxTable,
} from './ui'

type ToggleField = 'is_selected' | 'is_pk' | 'is_hash'

export function ColumnMappingTab() {
  const { data: tables, isLoading: tablesLoading, error: tablesError, reload } = useAsyncData(syncService.tables)
  const [tableSearch, setTableSearch] = useState('')
  const [columnSearch, setColumnSearch] = useState('')
  const [selectedId, setSelectedId] = useState('')
  const [tableName, setTableName] = useState('')
  const [columns, setColumns] = useState<TableColumn[]>([])
  const [columnsLoading, setColumnsLoading] = useState(false)
  const [columnsError, setColumnsError] = useState<string | null>(null)
  const [saving, setSaving] = useState<Set<string>>(new Set())
  const [actionError, setActionError] = useState<string | null>(null)

  const filteredTables = useMemo(() => {
    const query = tableSearch.trim().toLowerCase()
    const list = tables ?? []
    if (!query) return list
    return list.filter((table) => table.table_name.toLowerCase().includes(query))
  }, [tables, tableSearch])

  useEffect(() => {
    if (filteredTables.length > 0 && !filteredTables.some((t) => t.sync_table_id === selectedId)) {
      setSelectedId(filteredTables[0].sync_table_id)
    }
  }, [filteredTables, selectedId])

  useEffect(() => {
    if (!selectedId) return
    let active = true
    setColumnsLoading(true)
    setColumnsError(null)
    syncService.tableColumns(selectedId)
      .then((result) => {
        if (!active) return
        setTableName(result.table_name)
        setColumns(result.columns)
      })
      .catch((err) => {
        if (!active) return
        setColumnsError(err instanceof Error ? err.message : 'Failed to load columns')
      })
      .finally(() => { if (active) setColumnsLoading(false) })
    return () => { active = false }
  }, [selectedId])

  const stats = {
    total: columns.length,
    mapped: columns.filter((c) => c.is_selected).length,
    pk: columns.filter((c) => c.is_pk).length,
    hash: columns.filter((c) => c.is_hash).length,
  }

  const visibleColumns = useMemo(() => {
    const query = columnSearch.trim().toLowerCase()
    if (!query) return columns
    return columns.filter((column) => column.column_name.toLowerCase().includes(query))
  }, [columns, columnSearch])

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

  if (tablesLoading) return <TableSkeleton rows={6} columns={6} />
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
    <div className="sx-stack sx-mapping">
      <div className="row row-cols-2 row-cols-md-4 g-2">
        <div className="col"><SxStat icon="bi-list-columns" tone="indigo" value={stats.total} label="Columns" /></div>
        <div className="col"><SxStat icon="bi-check-circle" tone="success" value={stats.mapped} label="Mapped" /></div>
        <div className="col"><SxStat icon="bi-key" tone="warning" value={stats.pk} label="Primary Keys" /></div>
        <div className="col"><SxStat icon="bi-hash" tone="info" value={stats.hash} label="Hash Columns" /></div>
      </div>

      <div className="sx-split sx-mapping__split">
        <SxCard className="sx-pane sx-mapping__nav">
          <SxCardHead title="Tables" icon="bi-table" sub={`${filteredTables.length} visible`} />
          <SxCardBody flush>
            <div className="sx-mapping__search">
              <SxSearch value={tableSearch} onChange={setTableSearch} placeholder="Search tables..." ariaLabel="Search tables" />
            </div>
            <div className="sx-list">
              {filteredTables.map((table) => (
                <button
                  key={table.sync_table_id}
                  type="button"
                  className={`sx-list__item${table.sync_table_id === selectedId ? ' sx-list__item--active' : ''}`}
                  title={table.table_name}
                  onClick={() => setSelectedId(table.sync_table_id)}
                >
                  <span className="sx-mapping__table-name">{table.table_name}</span>
                  {table.is_active && <i className="bi bi-check-circle-fill sx-mapping__table-state" aria-hidden="true" />}
                </button>
              ))}
              {filteredTables.length === 0 && <div className="sx-dim small p-2">No tables match.</div>}
            </div>
          </SxCardBody>
        </SxCard>

        <SxCard className="sx-pane sx-mapping__main">
          <SxCardHead
            title={tableName || 'Columns'}
            icon="bi-diagram-3"
            sub={`${stats.mapped}/${stats.total} mapped`}
            action={<SxSearch value={columnSearch} onChange={setColumnSearch} placeholder="Search columns..." ariaLabel="Search columns" />}
          />
          <SxCardBody flush>
            {actionError && <div className="p-3 pb-0"><div className="sx-alert sx-alert--danger mb-0">{actionError}</div></div>}
            {columnsLoading ? (
              <div className="p-3"><TableSkeleton rows={6} columns={5} /></div>
            ) : columnsError ? (
              <div className="p-3"><ErrorState description={columnsError} onRetry={() => setSelectedId(selectedId)} /></div>
            ) : columns.length === 0 ? (
              <EmptyState
                icon="bi-diagram-3"
                title="No catalog columns"
                description="No discovered columns for this table yet. Register the store schema to populate the catalog."
              />
            ) : visibleColumns.length === 0 ? (
              <EmptyState icon="bi-search" title="No matching columns" description="Try a different column search." />
            ) : (
              <div className="sx-mapping__tablewrap">
                <SxTable>
                  <colgroup>
                    <col style={{ width: '58px' }} />
                    <col style={{ width: '27%' }} />
                    <col style={{ width: '27%' }} />
                    <col style={{ width: '112px' }} />
                    <col style={{ width: '112px' }} />
                    <col style={{ width: '56px' }} />
                    <col style={{ width: '56px' }} />
                  </colgroup>
                  <thead>
                    <tr>
                      <th>Sync</th>
                      <th>Store Column</th>
                      <th>HO Column</th>
                      <th>Store Type</th>
                      <th>HO Type</th>
                      <th>PK</th>
                      <th>Hash</th>
                    </tr>
                  </thead>
                  <tbody className="sx-mapping__tbody">
                    {visibleColumns.map((column) => (
                      <tr key={column.column_name} className="sx-mapping__row">
                        <td>
                          <ToggleCheck
                            checked={column.is_selected}
                            busy={saving.has(column.column_name)}
                            label={`Toggle sync for ${column.column_name}`}
                            onClick={() => toggle(column, 'is_selected')}
                          />
                        </td>
                        <td className="sx-strong sx-mapping__cellname" title={column.column_name}>{column.column_name}</td>
                        <td className="sx-dim sx-mapping__cellname" title={column.column_name}>{column.column_name}</td>
                        <td className="sx-dim"><span className="sx-mapping__dtype">{column.data_type}</span></td>
                        <td className="sx-dim"><span className="sx-mapping__dtype">{column.data_type}</span></td>
                        <td>
                          <ToggleCheck
                            checked={column.is_pk}
                            busy={saving.has(column.column_name)}
                            label={`Toggle primary key for ${column.column_name}`}
                            onClick={() => toggle(column, 'is_pk')}
                          />
                        </td>
                        <td>
                          <ToggleCheck
                            checked={column.is_hash}
                            busy={saving.has(column.column_name)}
                            label={`Toggle hash for ${column.column_name}`}
                            onClick={() => toggle(column, 'is_hash')}
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </SxTable>
              </div>
            )}
          </SxCardBody>
        </SxCard>
      </div>
    </div>
  )
}
