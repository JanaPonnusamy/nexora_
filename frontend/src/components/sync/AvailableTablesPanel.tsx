import { useEffect, useRef, useState } from 'react'
import { syncService } from '../../services/syncService'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { EmptyState } from '../common/EmptyState'
import { ErrorState } from '../common/ErrorState'
import { TableSkeleton } from '../common/TableSkeleton'
import type { AvailableTable } from '../../types/sync'
import { SxSearch, SxButton, SxChip, SxTable, SxPager } from './ui'
import { FilterBar } from '../../design-system/components/FilterBar'

const PAGE_SIZE = 20

/**
 * Browse the full discovered catalog (every source table) merged with its
 * configured state, so an admin can search and enable tables that are not yet
 * in the sync master (e.g. SalesRep, CategoryMaster). Search is server-side.
 */
export function AvailableTablesPanel({ onChanged }: { onChanged: () => void }) {
  const [search, setSearch] = useState('')
  const debounced = useDebouncedValue(search, 350)
  const [rows, setRows] = useState<AvailableTable[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [page, setPage] = useState(0)
  const ticket = useRef(0)

  const load = () => {
    const id = ++ticket.current
    setIsLoading(true)
    setError(null)
    syncService
      .availableTables(debounced.trim())
      .then((data) => {
        if (id !== ticket.current) return
        setRows(data)
        setPage(0)
      })
      .catch((err) => {
        if (id !== ticket.current) return
        setError(err instanceof Error ? err.message : 'Failed to load tables')
      })
      .finally(() => {
        if (id === ticket.current) setIsLoading(false)
      })
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(load, [debounced])

  const act = async (table: AvailableTable) => {
    setBusy(table.table_name)
    setError(null)
    try {
      if (!table.is_configured) {
        await syncService.createTable({
          table_name: table.table_name,
          sync_mode: 'UPSERT',
          watermark_column: null,
          window_days: null,
          custom_where: null,
          sync_order: 0,
          is_active: true,
        })
      } else {
        await syncService.setTableStatus(table.sync_table_id!, !table.is_active)
      }
      load()
      onChanged()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update table')
    } finally {
      setBusy(null)
    }
  }

  const totalPages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE))
  const clampedPage = Math.min(page, totalPages - 1)
  const pageRows = rows.slice(clampedPage * PAGE_SIZE, clampedPage * PAGE_SIZE + PAGE_SIZE)
  const rangeStart = rows.length === 0 ? 0 : clampedPage * PAGE_SIZE + 1
  const rangeEnd = Math.min(rows.length, clampedPage * PAGE_SIZE + PAGE_SIZE)

  const statusChip = (table: AvailableTable) => {
    if (!table.is_configured) return <SxChip tone="muted">Not configured</SxChip>
    return table.is_active ? <SxChip tone="success" dot>Enabled</SxChip> : <SxChip tone="warning" dot>Disabled</SxChip>
  }

  return (
    <>
      <FilterBar compact className="mb-3" ariaLabel="Available table filters">
        <SxSearch value={search} onChange={setSearch} placeholder="Search all source tables…" ariaLabel="Search all tables" />
        <span className="sx-card__sub">{rows.length.toLocaleString()} found</span>
      </FilterBar>

      {error && <div className="sx-alert sx-alert--danger">{error}</div>}

      {isLoading ? (
        <TableSkeleton rows={8} columns={3} />
      ) : error && rows.length === 0 ? (
        <ErrorState description={error} onRetry={load} />
      ) : rows.length === 0 ? (
        <EmptyState icon="bi-search" title="No tables found" description="Try a different search term." />
      ) : (
        <>
          <SxTable>
            <thead>
              <tr>
                <th>Status</th><th>Table</th><th>Sync Mode</th><th className="sx-num">Action</th>
              </tr>
            </thead>
            <tbody>
              {pageRows.map((table) => (
                <tr key={`${table.schema_name}.${table.table_name}`}>
                  <td>{statusChip(table)}</td>
                  <td className="sx-strong">
                    {table.table_name}
                    <span className="sx-dim" style={{ fontWeight: 400 }}> · {table.schema_name}</span>
                  </td>
                  <td className="sx-dim">{table.sync_mode ?? '—'}</td>
                  <td className="sx-num">
                    {!table.is_configured ? (
                      <SxButton variant="primary" sm icon="bi-plus-lg" busy={busy === table.table_name} onClick={() => act(table)}>Enable</SxButton>
                    ) : table.is_active ? (
                      <SxButton variant="ghost" sm icon="bi-pause" busy={busy === table.table_name} onClick={() => act(table)}>Disable</SxButton>
                    ) : (
                      <SxButton variant="success" sm icon="bi-check-lg" busy={busy === table.table_name} onClick={() => act(table)}>Enable</SxButton>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </SxTable>
          <SxPager rangeStart={rangeStart} rangeEnd={rangeEnd} total={rows.length} page={clampedPage} totalPages={totalPages} onPage={setPage} noun="tables" />
        </>
      )}
    </>
  )
}
