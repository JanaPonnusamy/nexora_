import { useCallback, useEffect, useState } from 'react'
import { useActingUser } from '../../hooks/useActingUser'
import { productMappingService } from '../../services/productMappingService'
import type { MappingDashboard, RunSummary } from '../../types/productMapping'
import { ErrorState } from '../common/ErrorState'
import { SxButton, SxCard, SxCardBody, SxCardHead, SxStat } from '../sync/ui'
import { RequireStorePair, type MappingCtx } from './shared'

export function DashboardTab({ ctx }: { ctx: MappingCtx }) {
  const actingUser = useActingUser()
  const [dash, setDash] = useState<MappingDashboard | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const [lastRun, setLastRun] = useState<RunSummary | null>(null)
  const [runError, setRunError] = useState<string | null>(null)

  const loadDash = useCallback(() => {
    if (!ctx.tenantId) return
    setError(null)
    productMappingService
      .dashboard(ctx.tenantId, ctx.sourceStoreId || undefined, ctx.targetStoreId || undefined)
      .then(setDash)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load dashboard'))
  }, [ctx.tenantId, ctx.sourceStoreId, ctx.targetStoreId])

  useEffect(() => { loadDash() }, [loadDash])

  const runMapping = async () => {
    setRunning(true)
    setRunError(null)
    setLastRun(null)
    try {
      const summary = await productMappingService.run(
        ctx.tenantId, ctx.sourceStoreId, ctx.targetStoreId, actingUser || null)
      setLastRun(summary)
      loadDash()
    } catch (e) {
      setRunError(e instanceof Error ? e.message : 'Mapping run failed')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="sx-stack">
      <SxCard>
        <SxCardHead
          title="Run Product Mapping"
          icon="bi-play-circle"
          sub={ctx.sourceStoreId && ctx.targetStoreId ? `${ctx.sourceLabel} → ${ctx.targetLabel}` : 'Select a store pair above'}
          action={
            <SxButton
              variant="primary"
              icon="bi-lightning-charge"
              busy={running}
              disabled={!ctx.sourceStoreId || !ctx.targetStoreId}
              onClick={runMapping}
            >
              {running ? 'Mapping…' : 'Run Mapping'}
            </SxButton>
          }
        />
        <SxCardBody>
          <p className="sx-dim" style={{ margin: 0, fontSize: '0.86rem' }}>
            Runs all seven phases in order — supplier map, exact name, normalized name,
            structured attributes, then candidate search, ranking and fuzzy — over products
            not already matched. Existing approved matches are never overwritten, and
            ProductCode is never used on its own.
          </p>
          {runError && <div className="mt-3"><ErrorState description={runError} onRetry={runMapping} /></div>}
          {lastRun && (
            <div className="row row-cols-2 row-cols-md-4 g-3 mt-1">
              <div className="col"><SxStat icon="bi-lightning-charge" tone="success" value={lastRun.auto} label="Auto-matched" /></div>
              <div className="col"><SxStat icon="bi-hourglass-split" tone="warning" value={lastRun.pending} label="Needs review" /></div>
              <div className="col"><SxStat icon="bi-shield-check" tone="indigo" value={lastRun.preserved} label="Preserved" /></div>
              <div className="col"><SxStat icon="bi-box-seam" tone="muted" value={lastRun.source_count} label="Source products" sub={`${lastRun.supplier_pairs} supplier pairs`} /></div>
            </div>
          )}
        </SxCardBody>
      </SxCard>

      <RequireStorePair ctx={ctx}>
        {error ? <ErrorState description={error} onRetry={loadDash} /> : dash && (
          <>
            <div className="row row-cols-2 row-cols-md-4 g-3">
              <div className="col"><SxStat icon="bi-diagram-3" tone="indigo" value={dash.total} label="Total mappings" /></div>
              <div className="col"><SxStat icon="bi-check2-circle" tone="success" value={dash.matched} label="Matched" sub={`${dash.match_rate}% of total`} /></div>
              <div className="col"><SxStat icon="bi-hourglass-split" tone="warning" value={dash.needs_review} label="Needs review" /></div>
              <div className="col"><SxStat icon="bi-x-circle" tone="muted" value={dash.counts.REJECTED} label="Rejected" /></div>
            </div>
            <div className="row row-cols-2 row-cols-md-4 g-3">
              <div className="col"><SxStat icon="bi-lightning-charge" tone="success" value={dash.counts.AUTO} label="Auto matches" /></div>
              <div className="col"><SxStat icon="bi-hand-thumbs-up" tone="indigo" value={dash.counts.APPROVED} label="Approved" /></div>
              <div className="col"><SxStat icon="bi-inbox" tone="warning" value={dash.counts.PENDING} label="Pending" /></div>
            </div>
          </>
        )}
      </RequireStorePair>
    </div>
  )
}
