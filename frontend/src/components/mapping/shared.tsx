import type { ReactNode } from 'react'
import { SxChip } from '../sync/ui'
import { EmptyState } from '../common/EmptyState'
import type { Mapping, MappingStatus, MatchMethod } from '../../types/productMapping'

/** Selection context shared by every Product Mapping tab. */
export interface MappingCtx {
  tenantId: string
  sourceStoreId: string
  targetStoreId: string
  sourceLabel: string
  targetLabel: string
}

const STATUS_TONE: Record<MappingStatus, 'success' | 'warning' | 'indigo' | 'muted'> = {
  AUTO: 'success',
  APPROVED: 'indigo',
  PENDING: 'warning',
  REJECTED: 'muted',
}

export function StatusChip({ status }: { status: MappingStatus }) {
  return <SxChip tone={STATUS_TONE[status]} dot>{status}</SxChip>
}

export function MethodChip({ method }: { method: MatchMethod }) {
  if (!method) return <span className="sx-dim">—</span>
  const tone = method === 'SUPPLIER' || method === 'EXACT' ? 'success'
    : method === 'FUZZY' ? 'warning' : 'default'
  return <SxChip tone={tone}>{method}</SxChip>
}

export function ConfidenceChip({ value, dot }: { value: number; dot?: boolean }) {
  const tone = value >= 98 ? 'success' : value >= 96 ? 'indigo' : value >= 94 ? 'warning' : 'muted'
  return <SxChip tone={tone} dot={dot}>{value.toFixed(0)}%</SxChip>
}

export function ProductCell({ code, name }: { code: string | null; name: string | null }) {
  if (!name && !code) return <span className="sx-dim">—</span>
  return (
    <div className="sx-rowlabel">
      <span className="sx-rowlabel__main">{name || '—'}</span>
      <span className="sx-rowlabel__sub">Code {code ?? '—'}</span>
    </div>
  )
}

export function AttrCell({ m }: { m: Mapping }) {
  const bits = [m.brand, m.strength && `${m.strength}${m.unit ?? ''}`, m.dosage_form]
    .filter(Boolean)
    .join(' · ')
  return bits ? <span className="sx-dim" style={{ fontSize: '0.82rem' }}>{bits}</span>
    : <span className="sx-dim">—</span>
}

export function Money({ value }: { value: number | null }) {
  if (value == null) return <span className="sx-dim">—</span>
  return <>{value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</>
}

/** Wrap a tab body so it shows a friendly prompt until a store pair is chosen. */
export function RequireStorePair({ ctx, children }: { ctx: MappingCtx; children: ReactNode }) {
  if (!ctx.sourceStoreId || !ctx.targetStoreId) {
    return (
      <EmptyState
        icon="bi-arrow-left-right"
        title="Choose a store pair"
        description="Pick a source and target store above to map products between them."
      />
    )
  }
  return <>{children}</>
}
