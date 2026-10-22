import { useEffect, useState } from 'react'
import { PageHeader } from '../../components/common/PageHeader'
import { EmptyState } from '../../components/common/EmptyState'
import { ErrorState } from '../../components/common/ErrorState'
import { FilterBar, FilterSearch } from '../../design-system/components/FilterBar'
import { DataTable } from '../../components/common/DataTable/DataTable'
import { ApiError } from '../../services/apiClient'
import { procurementService } from '../../services/procurementService'
import { isVplHistoryScreenEnabled } from './vplHistoryFlag'
import {
  applyFailure,
  applySaveFailure,
  applySaveSuccess,
  applyVersionConflict,
  applyWorking,
  confirmRefresh,
  createScreen,
  displayQty,
  moveSelection,
  requestRefresh,
  retry,
  switchContext,
  type VplScreenState,
} from './vplHistorySession'

/**
 * Isolated VPL history screen. Flag defaults off. It reads and edits only
 * /api/procurement/vpl-history. It does not call live generation.
 */
export default function VplHistoryScreenPage() {
  const enabled = isVplHistoryScreenEnabled()
  const [tenantId, setTenantId] = useState('')
  const [storeId, setStoreId] = useState('')
  const [cycleId, setCycleId] = useState('')
  const [draftQty, setDraftQty] = useState('')
  const [screen, setScreen] = useState<VplScreenState>(() => createScreen('', '', '', enabled))

  useEffect(() => {
    if (!enabled || !tenantId || !storeId || !cycleId) return
    const requestId = screen.requestId
    if (screen.status !== 'loading') return
    let cancelled = false
    Promise.all([
      procurementService.vplWorking(tenantId, storeId, cycleId),
      procurementService.vplHistoryList(tenantId, storeId, 10),
    ])
      .then(([body, history]) => {
        if (cancelled) return
        setScreen((current) => applyWorking(current, requestId, body, history.headers))
      })
      .catch((err) => {
        if (cancelled) return
        const message = err instanceof ApiError ? err.message : 'The working set could not be loaded.'
        setScreen((current) => applyFailure(current, requestId, message))
      })
    return () => {
      cancelled = true
    }
  }, [enabled, tenantId, storeId, cycleId, screen.requestId, screen.status])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'ArrowDown') setScreen((current) => moveSelection(current, 1))
      if (event.key === 'ArrowUp') setScreen((current) => moveSelection(current, -1))
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const changeContext = (nextTenant: string, nextStore: string, nextCycle: string) => {
    setTenantId(nextTenant)
    setStoreId(nextStore)
    setCycleId(nextCycle)
    setScreen((current) => switchContext(current, nextTenant, nextStore, nextCycle))
  }

  const saveQty = async () => {
    const selected = screen.lines.find((line) => line.product_code === screen.selectedCode)
    if (!selected) return
    const qty = Number(draftQty)
    if (!Number.isFinite(qty)) return
    try {
      const saved = await procurementService.vplEditLine(tenantId, storeId, cycleId, {
        product_code: selected.product_code,
        expected_version: selected.row_version,
        editor_id: 'screen',
        changes: { final_qty: qty },
      })
      setScreen((current) => applySaveSuccess(current, selected.product_code, saved.final_qty ?? qty, saved.row_version))
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setScreen((current) => applyVersionConflict(current))
        return
      }
      setScreen((current) => applySaveFailure(current))
    }
  }

  if (!enabled) {
    return (
      <div className="page-content">
        <PageHeader title="VPL history" breadcrumb={['Procurement', 'VPL history']} description="This screen is off." />
        <EmptyState icon="bi-toggle-off" title="VPL history is off" description="Set nexora.vplHistoryScreen to 1, or VITE_VPL_HISTORY_SCREEN=1. PROCUREMENT_ADMIN is still required." />
      </div>
    )
  }

  const rows = screen.lines

  return (
    <div className="page-content">
      <PageHeader
        title="VPL history"
        breadcrumb={['Procurement', 'VPL history']}
        description="Process memory only. Live generation is not called. Stock and product name are unavailable because this API does not return them."
      />
      <FilterBar ariaLabel="VPL store and cycle">
        <FilterSearch value={tenantId} onChange={(value) => changeContext(value, storeId, cycleId)} placeholder="Tenant" ariaLabel="Tenant" />
        <FilterSearch value={storeId} onChange={(value) => changeContext(tenantId, value, cycleId)} placeholder="Store" ariaLabel="Store" />
        <FilterSearch value={cycleId} onChange={(value) => changeContext(tenantId, storeId, value)} placeholder="Cycle" ariaLabel="Cycle" />
      </FilterBar>
      <p>Refresh {screen.refreshId ?? 'unavailable'} · snapshot {screen.ruleSnapshotId ?? 'unavailable'}</p>
      {screen.status === 'loading' && <EmptyState icon="bi-hourglass" title="Loading" description="The previous store is not shown." />}
      {screen.status === 'empty' && <EmptyState icon="bi-inbox" title="No working lines" description="This store cycle has no VPL rows in memory." />}
      {screen.status === 'error' && <ErrorState title="VPL history" description={screen.error ?? 'Load failed.'} onRetry={() => setScreen((current) => retry(current))} />}
      {screen.status === 'conflict' && (
        <ErrorState title="Version conflict" description={screen.conflict ?? 'Reload required.'} onRetry={() => setScreen((current) => retry(current))} />
      )}
      {screen.status === 'ready' && (
        <>
          <DataTable
            columns={[
              { key: 'product_code', header: 'Product code' },
              { key: 'name', header: 'Name', accessor: () => 'unavailable' },
              { key: 'suggested_qty', header: 'Suggested', accessor: (row) => displayQty(row.suggested_qty) },
              { key: 'final_qty', header: 'Final', accessor: (row) => displayQty(row.final_qty) },
              { key: 'row_version', header: 'Version' },
            ]}
            data={rows}
            getRowId={(row) => row.product_code}
            activeRowId={screen.selectedCode ?? undefined}
          />
          <label>
            Final quantity
            <input aria-label="Final quantity" value={draftQty} onChange={(event) => setDraftQty(event.target.value)} />
          </label>
          <button type="button" onClick={() => void saveQty()}>Save final quantity</button>
          {screen.saved && <p>Saved</p>}
          <button type="button" onClick={() => setScreen((current) => requestRefresh(current))}>Refresh</button>
          {screen.refreshNeedsConfirm && (
            <button type="button" onClick={() => setScreen((current) => confirmRefresh(current))}>Confirm refresh</button>
          )}
          <h2>Manual Review — Removed From Latest Generation</h2>
          <ul>
            {screen.removed.map((line) => (
              <li key={line.product_code}>
                {line.product_code} final {displayQty(line.final_qty)} supplier {line.supplier_code ?? 'unavailable'} — not orderable
              </li>
            ))}
          </ul>
          <h2>History</h2>
          <ul>
            {screen.history.map((batch) => (
              <li key={batch.history_id}>{batch.history_id} · {batch.line_count} lines · read only</li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}
