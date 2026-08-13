import { useMemo, useState } from 'react'
import { useAsyncData } from '../../hooks/useAsyncData'
import { syncService } from '../../services/syncService'
import { EmptyState } from '../common/EmptyState'
import { ErrorState } from '../common/ErrorState'
import { TableSkeleton } from '../common/TableSkeleton'
import { SyncTableFormModal } from './SyncTableFormModal'
import { AvailableTablesPanel } from './AvailableTablesPanel'
import { ToggleCheck } from '../dashboard/ToggleCheck'
import { SyncTypeBadge } from './SyncBadges'
import type { SyncTable } from '../../types/sync'
import {
  SxCard, SxCardHead, SxCardBody, SxStat, SxButton, SxSearch, SxSegmented, SxPager, SxTable,
} from './ui'
import { FilterBar } from '../../design-system/components/FilterBar'

type ModalState = { mode: 'create' } | { mode: 'edit'; table: SyncTable } | null
type StatusFilter = 'all' | 'enabled' | 'disabled'
type ModeFilter = 'all' | 'UPSERT' | 'ROLLING_WINDOW'
type Scope = 'configured' | 'available'

const PAGE_SIZE = 20

export function TableConfigTab() {
  const { data, isLoading, error, reload } = useAsyncData(syncService.tables)
  const [modal, setModal] = useState<ModalState>(null)
  const [togglingId, setTogglingId] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [workflowBusy, setWorkflowBusy] = useState<'populate' | 'promote' | null>(null)
  const [workflowMessage, setWorkflowMessage] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [modeFilter, setModeFilter] = useState<ModeFilter>('all')
  const [page, setPage] = useState(0)
  const [scope, setScope] = useState<Scope>('configured')

  const tables = data ?? []
  const stats = {
    total: tables.length,
    enabled: tables.filter((t) => t.is_active).length,
    disabled: tables.filter((t) => !t.is_active).length,
    upsert: tables.filter((t) => t.sync_mode === 'UPSERT').length,
    rolling: tables.filter((t) => t.sync_mode === 'ROLLING_WINDOW').length,
  }

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase()
    return tables.filter((table) => {
      if (statusFilter === 'enabled' && !table.is_active) return false
      if (statusFilter === 'disabled' && table.is_active) return false
      if (modeFilter !== 'all' && table.sync_mode !== modeFilter) return false
      if (query && !table.table_name.toLowerCase().includes(query)) return false
      return true
    })
  }, [tables, search, statusFilter, modeFilter])

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const clampedPage = Math.min(page, totalPages - 1)
  const pageRows = filtered.slice(clampedPage * PAGE_SIZE, clampedPage * PAGE_SIZE + PAGE_SIZE)
  const rangeStart = filtered.length === 0 ? 0 : clampedPage * PAGE_SIZE + 1
  const rangeEnd = Math.min(filtered.length, clampedPage * PAGE_SIZE + PAGE_SIZE)
  const resetPage = () => setPage(0)

  const toggleEnabled = async (table: SyncTable) => {
    setTogglingId(table.sync_table_id)
    setActionError(null)
    try {
      await syncService.setTableStatus(table.sync_table_id, !table.is_active)
      await reload()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to update table')
    } finally { setTogglingId(null) }
  }

  const runPopulate = async () => {
    setWorkflowBusy('populate'); setActionError(null); setWorkflowMessage(null)
    try {
      const result = await syncService.populateRegistry()
      setWorkflowMessage(`Registry populated: ${result.new_tables} new (${result.tables_discovered} discovered, ${result.total_registry_tables} in registry).`)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to populate registry')
    } finally { setWorkflowBusy(null) }
  }

  const runPromote = async () => {
    setWorkflowBusy('promote'); setActionError(null); setWorkflowMessage(null)
    try {
      const result = await syncService.promoteTables()
      setWorkflowMessage(`Promoted ${result.promoted_tables} table(s) to master (${result.total_master_tables} total).`)
      await reload()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to promote tables')
    } finally { setWorkflowBusy(null) }
  }

  if (isLoading) return <TableSkeleton rows={8} columns={6} />
  if (error || !data) return <ErrorState description={error ?? 'Failed to load tables'} onRetry={reload} />

  return (
    <div className="sx-stack">
      <div className="row row-cols-2 row-cols-md-3 row-cols-xl-5 g-2">
        <div className="col"><SxStat icon="bi-table" tone="indigo" value={stats.total} label="Total Tables" /></div>
        <div className="col"><SxStat icon="bi-check-circle" tone="success" value={stats.enabled} label="Enabled" /></div>
        <div className="col"><SxStat icon="bi-pause-circle" tone="muted" value={stats.disabled} label="Disabled" /></div>
        <div className="col"><SxStat icon="bi-arrow-repeat" tone="teal" value={stats.upsert} label="Upsert" /></div>
        <div className="col"><SxStat icon="bi-clock-history" tone="violet" value={stats.rolling} label="Rolling Window" /></div>
      </div>

      <SxCard className="sx-pane">
        <SxCardHead title="Sync Tables" icon="bi-table"
          sub={scope === 'configured' ? `${filtered.length} shown` : 'browse the full source catalog'}
          action={
            <div className="d-flex gap-2 flex-wrap align-items-center">
              <SxSegmented ariaLabel="Table view" value={scope}
                onChange={(v) => setScope(v)}
                options={[{ label: 'Configured', value: 'configured' }, { label: 'All Tables', value: 'available' }]} />
              {scope === 'configured' && (
                <>
                  <SxButton sm variant="ghost" icon="bi-arrow-down-up" busy={workflowBusy === 'populate'} disabled={workflowBusy !== null} onClick={runPopulate}>Populate</SxButton>
                  <SxButton sm variant="ghost" icon="bi-arrow-up-circle" busy={workflowBusy === 'promote'} disabled={workflowBusy !== null} onClick={runPromote}>Promote</SxButton>
                  <SxButton sm variant="primary" icon="bi-plus-lg" onClick={() => setModal({ mode: 'create' })}>Add</SxButton>
                </>
              )}
            </div>
          } />
        {scope === 'available' ? (
          <SxCardBody>
            <AvailableTablesPanel onChanged={reload} />
          </SxCardBody>
        ) : (
        <>
        <SxCardBody>
          <FilterBar compact className="mb-3" ariaLabel="Configured table filters">
            <SxSearch value={search} onChange={(v) => { setSearch(v); resetPage() }} placeholder="Search tables…" ariaLabel="Search tables" />
            <SxSegmented ariaLabel="Status" value={statusFilter}
              onChange={(v) => { setStatusFilter(v); resetPage() }}
              options={[{ label: 'All', value: 'all' }, { label: 'Enabled', value: 'enabled' }, { label: 'Disabled', value: 'disabled' }]} />
            <SxSegmented ariaLabel="Mode" value={modeFilter}
              onChange={(v) => { setModeFilter(v); resetPage() }}
              options={[{ label: 'All', value: 'all' }, { label: 'Upsert', value: 'UPSERT' }, { label: 'Rolling', value: 'ROLLING_WINDOW' }]} />
          </FilterBar>

          {workflowMessage && <div className="sx-alert sx-alert--info">{workflowMessage}</div>}
          {actionError && <div className="sx-alert sx-alert--danger">{actionError}</div>}

          {tables.length === 0 ? (
            <EmptyState icon="bi-table" title="No tables configured"
              description="Populate the registry and promote discovered tables, or add one from the catalog."
              action={{ label: 'Add Table', icon: 'bi-plus-lg', onClick: () => setModal({ mode: 'create' }) }} />
          ) : filtered.length === 0 ? (
            <EmptyState icon="bi-search" title="No matching tables" description="Try adjusting your search or filters." />
          ) : null}
        </SxCardBody>

        {filtered.length > 0 && (
          <>
            <SxCardBody flush>
              <SxTable>
                <thead>
                  <tr>
                    <th>Enabled</th><th>Table Name</th><th>Sync Mode</th><th>Watermark</th>
                    <th className="sx-num">Window</th><th>Custom Where</th><th className="sx-num">Order</th><th className="sx-num">Edit</th>
                  </tr>
                </thead>
                <tbody>
                  {pageRows.map((table) => (
                    <tr key={table.sync_table_id}>
                      <td><ToggleCheck checked={table.is_active} busy={togglingId === table.sync_table_id}
                        label={`${table.is_active ? 'Disable' : 'Enable'} ${table.table_name}`} onClick={() => toggleEnabled(table)} /></td>
                      <td className="sx-strong">{table.table_name}</td>
                      <td><SyncTypeBadge value={table.sync_mode} /></td>
                      <td className="sx-dim">{table.watermark_column ?? '—'}</td>
                      <td className="sx-num">{table.window_days ?? '—'}</td>
                      <td className="sx-dim" style={{ maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{table.custom_where ?? '—'}</td>
                      <td className="sx-num">{table.sync_order}</td>
                      <td className="sx-num">
                        <SxButton variant="ghost" sm icon="bi-pencil" title={`Edit ${table.table_name}`} onClick={() => setModal({ mode: 'edit', table })} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </SxTable>
            </SxCardBody>
            <SxPager rangeStart={rangeStart} rangeEnd={rangeEnd} total={filtered.length} page={clampedPage} totalPages={totalPages} onPage={setPage} noun="tables" />
          </>
        )}
        </>
        )}
      </SxCard>

      {modal && (
        <SyncTableFormModal
          mode={modal.mode}
          table={modal.mode === 'edit' ? modal.table : undefined}
          onClose={() => setModal(null)}
          onSaved={() => { setModal(null); void reload() }}
        />
      )}
    </div>
  )
}
