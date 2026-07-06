import { useAsyncData } from '../../hooks/useAsyncData'
import { productMappingService } from '../../services/productMappingService'
import { formatDateTime } from '../../utils/format'
import { EmptyState } from '../common/EmptyState'
import { ErrorState } from '../common/ErrorState'
import { TableSkeleton } from '../common/TableSkeleton'
import { SxCard, SxCardBody, SxCardHead, SxChip, SxTable } from '../sync/ui'
import type { MappingCtx } from './shared'

const ACTION_TONE: Record<string, 'success' | 'warning' | 'indigo' | 'muted' | 'danger'> = {
  RUN: 'muted', AUTO_MATCH: 'success', APPROVE: 'indigo', REJECT: 'danger', REMAP: 'warning',
}

export function AuditLogTab({ ctx }: { ctx: MappingCtx }) {
  const { data, isLoading, error, reload } = useAsyncData(() =>
    productMappingService.audit(ctx.tenantId))

  return (
    <SxCard>
      <SxCardHead title="Audit Log" icon="bi-clock-history" sub="Every mapping state change" />
      <SxCardBody flush>
        {isLoading ? <TableSkeleton rows={8} columns={4} />
          : error || !data ? <ErrorState description={error ?? 'Failed to load audit log'} onRetry={reload} />
          : data.length === 0 ? <EmptyState icon="bi-clock-history" title="No activity yet" description="Runs, approvals and rejections are recorded here." />
          : (
            <SxTable>
              <thead><tr><th>When</th><th>Action</th><th>Transition</th><th>Detail</th></tr></thead>
              <tbody>
                {data.map((a) => (
                  <tr key={a.audit_id}>
                    <td className="sx-dim" style={{ fontSize: '0.82rem' }}>{formatDateTime(a.created_at)}</td>
                    <td><SxChip tone={ACTION_TONE[a.action] ?? 'default'}>{a.action}</SxChip></td>
                    <td className="sx-dim" style={{ fontSize: '0.82rem' }}>
                      {a.old_status ? `${a.old_status} → ` : ''}{a.new_status ?? '—'}
                    </td>
                    <td className="sx-dim" style={{ fontSize: '0.82rem' }}>{a.detail ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </SxTable>
          )}
      </SxCardBody>
    </SxCard>
  )
}
