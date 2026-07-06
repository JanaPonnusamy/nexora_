import { useAsyncData } from '../../hooks/useAsyncData'
import { productMappingService } from '../../services/productMappingService'
import { ErrorState } from '../common/ErrorState'
import { TableSkeleton } from '../common/TableSkeleton'
import { SxCard, SxCardBody, SxCardHead, SxChip, SxTable } from '../sync/ui'
import { RequireStorePair, type MappingCtx } from './shared'

const METHOD_ORDER = ['SUPPLIER', 'EXACT', 'NORMALIZED', 'STRUCTURED', 'FUZZY', 'MANUAL', 'UNMATCHED']

export function StatisticsTab({ ctx }: { ctx: MappingCtx }) {
  const { data, isLoading, error, reload } = useAsyncData(() =>
    productMappingService.statistics(ctx.tenantId, ctx.sourceStoreId || undefined, ctx.targetStoreId || undefined))

  return (
    <RequireStorePair ctx={ctx}>
      {isLoading ? <TableSkeleton rows={6} columns={2} />
        : error || !data ? <ErrorState description={error ?? 'Failed to load statistics'} onRetry={reload} />
        : (
          <div className="row g-3">
            <div className="col-12 col-lg-6">
              <SxCard>
                <SxCardHead title="By Status" icon="bi-pie-chart" />
                <SxCardBody flush>
                  <SxTable>
                    <thead><tr><th>Status</th><th className="sx-num">Count</th></tr></thead>
                    <tbody>
                      {Object.entries(data.by_status).map(([k, v]) => (
                        <tr key={k}><td>{k}</td><td className="sx-num">{v}</td></tr>
                      ))}
                    </tbody>
                  </SxTable>
                </SxCardBody>
              </SxCard>
            </div>
            <div className="col-12 col-lg-6">
              <SxCard>
                <SxCardHead title="By Match Method" icon="bi-diagram-3" sub="Which phase produced each mapping" />
                <SxCardBody flush>
                  <SxTable>
                    <thead><tr><th>Method / Phase</th><th className="sx-num">Count</th></tr></thead>
                    <tbody>
                      {METHOD_ORDER.filter((m) => data.by_method[m] != null).map((m) => (
                        <tr key={m}>
                          <td><SxChip tone={m === 'FUZZY' ? 'warning' : m === 'UNMATCHED' ? 'muted' : 'default'}>{m}</SxChip></td>
                          <td className="sx-num">{data.by_method[m]}</td>
                        </tr>
                      ))}
                    </tbody>
                  </SxTable>
                </SxCardBody>
              </SxCard>
            </div>
          </div>
        )}
    </RequireStorePair>
  )
}
