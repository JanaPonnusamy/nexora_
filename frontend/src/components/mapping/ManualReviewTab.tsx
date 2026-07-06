import { useCallback, useEffect, useState } from 'react'
import { useActingUser } from '../../hooks/useActingUser'
import { productMappingService } from '../../services/productMappingService'
import type { Candidate, Mapping, MappingDetail } from '../../types/productMapping'
import { EmptyState } from '../common/EmptyState'
import { ErrorState } from '../common/ErrorState'
import { TableSkeleton } from '../common/TableSkeleton'
import { SxButton, SxCard, SxCardBody, SxCardHead, SxChip, SxTable } from '../sync/ui'
import { AttrCell, ConfidenceChip, Money, ProductCell, RequireStorePair, type MappingCtx } from './shared'

export function ManualReviewTab({ ctx }: { ctx: MappingCtx }) {
  const actingUser = useActingUser()
  const [pending, setPending] = useState<Mapping[]>([])
  const [selected, setSelected] = useState<MappingDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const loadPending = useCallback(() => {
    setLoading(true)
    setError(null)
    productMappingService
      .mappings(ctx.tenantId, {
        status: 'PENDING',
        source_store_id: ctx.sourceStoreId,
        target_store_id: ctx.targetStoreId,
        page: 1,
        page_size: 100,
      })
      .then((res) => setPending(res.items))
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load review queue'))
      .finally(() => setLoading(false))
  }, [ctx.tenantId, ctx.sourceStoreId, ctx.targetStoreId])

  useEffect(() => { loadPending() }, [loadPending])

  const openMapping = (m: Mapping) => {
    setSelected(null)
    productMappingService.mapping(ctx.tenantId, m.mapping_id).then(setSelected).catch(() => setSelected(null))
  }

  const afterAction = () => {
    setSelected(null)
    loadPending()
  }

  const approveCandidate = async (c: Candidate) => {
    if (!selected) return
    setBusy(true)
    try {
      await productMappingService.approve(ctx.tenantId, selected.mapping_id, {
        target_product_code: c.target_product_code,
        target_product_name: c.target_product_name,
        actor: actingUser || null,
      })
      afterAction()
    } finally { setBusy(false) }
  }

  const rejectMapping = async () => {
    if (!selected) return
    setBusy(true)
    try {
      await productMappingService.reject(ctx.tenantId, selected.mapping_id, actingUser || null)
      afterAction()
    } finally { setBusy(false) }
  }

  if (loading) return <RequireStorePair ctx={ctx}><TableSkeleton rows={6} columns={4} /></RequireStorePair>

  return (
    <RequireStorePair ctx={ctx}>
      {error ? <ErrorState description={error} onRetry={loadPending} /> : (
        <div className="row g-3">
          {/* Review queue */}
          <div className="col-12 col-lg-5">
            <SxCard>
              <SxCardHead title="Review Queue" icon="bi-inbox" sub={`${pending.length} pending`} />
              <SxCardBody flush>
                {pending.length === 0
                  ? <EmptyState icon="bi-check2-all" title="Nothing to review" description="Every product is matched or approved for this store pair." />
                  : (
                    <SxTable>
                      <thead><tr><th>Source Product</th><th>Attributes</th><th className="sx-num">Best</th></tr></thead>
                      <tbody>
                        {pending.map((m) => (
                          <tr
                            key={m.mapping_id}
                            onClick={() => openMapping(m)}
                            className={selected?.mapping_id === m.mapping_id ? 'sx-row--active' : ''}
                            style={{ cursor: 'pointer' }}
                          >
                            <td><ProductCell code={m.source_product_code} name={m.source_product_name} /></td>
                            <td><AttrCell m={m} /></td>
                            <td className="sx-num"><ConfidenceChip value={m.confidence} /></td>
                          </tr>
                        ))}
                      </tbody>
                    </SxTable>
                  )}
              </SxCardBody>
            </SxCard>
          </div>

          {/* Candidate detail */}
          <div className="col-12 col-lg-7">
            {!selected ? (
              <SxCard><SxCardBody>
                <EmptyState icon="bi-hand-index" title="Select a product" description="Choose a product from the review queue to compare candidates and approve the correct match." />
              </SxCardBody></SxCard>
            ) : (
              <SxCard>
                <SxCardHead
                  title={selected.source_product_name}
                  icon="bi-diagram-3"
                  sub={`Code ${selected.source_product_code} · ${ctx.sourceLabel} → ${ctx.targetLabel}`}
                  action={<SxButton variant="danger" sm icon="bi-x-circle" busy={busy} onClick={rejectMapping}>Reject</SxButton>}
                />
                <SxCardBody flush>
                  {selected.candidates.length === 0
                    ? <EmptyState icon="bi-search" title="No candidates" description="The engine found no similar product in the target store. Reject, or map manually later." />
                    : (
                      <SxTable>
                        <thead>
                          <tr>
                            <th>Candidate</th><th>Brand / Strength / Form</th>
                            <th className="sx-num">MRP</th><th>Reason</th>
                            <th className="sx-num">Score</th><th></th>
                          </tr>
                        </thead>
                        <tbody>
                          {selected.candidates.map((c) => (
                            <tr key={c.candidate_id}>
                              <td><ProductCell code={c.target_product_code} name={c.target_product_name} /></td>
                              <td>
                                <span className="sx-dim" style={{ fontSize: '0.82rem' }}>
                                  {[c.brand, c.strength, c.dosage_form].filter(Boolean).join(' · ') || '—'}
                                </span>
                              </td>
                              <td className="sx-num"><Money value={c.mrp} /></td>
                              <td><span className="sx-dim" style={{ fontSize: '0.8rem' }}>{c.reason ?? '—'}</span></td>
                              <td className="sx-num"><SxChip tone={c.total_score >= 80 ? 'success' : c.total_score >= 50 ? 'warning' : 'muted'}>{c.total_score.toFixed(0)}</SxChip></td>
                              <td><SxButton variant="success" sm icon="bi-check2" busy={busy} onClick={() => approveCandidate(c)}>Approve</SxButton></td>
                            </tr>
                          ))}
                        </tbody>
                      </SxTable>
                    )}
                </SxCardBody>
              </SxCard>
            )}
          </div>
        </div>
      )}
    </RequireStorePair>
  )
}
