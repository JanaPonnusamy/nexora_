import { useEffect, useState } from 'react'
import { productMappingService } from '../../services/productMappingService'
import type { Candidate, Mapping, MappingDetail, ProductSearchResult } from '../../types/productMapping'
import { ConfidenceChip, Money, ProductCell } from './shared'

/** Right-side inspection drawer for one mapping row — the "How Matched" debug
 *  view. Reuses the existing mapping-detail + candidates data (GET
 *  /mappings/{id}) rather than a new endpoint. */
export function MatchLogicDrawer({
  tenantId,
  mapping,
  onUseCandidate,
  onClose,
}: {
  tenantId: string
  mapping: Mapping
  onUseCandidate: (product: ProductSearchResult) => void
  onClose: () => void
}) {
  const [detail, setDetail] = useState<MappingDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    setLoading(true)
    setError(null)
    productMappingService
      .mapping(tenantId, mapping.mapping_id)
      .then((d) => { if (live) setDetail(d) })
      .catch((e) => { if (live) setError(e instanceof Error ? e.message : 'Failed to load match details') })
      .finally(() => { if (live) setLoading(false) })
    return () => { live = false }
  }, [tenantId, mapping.mapping_id])

  const onKeyDown = (e: React.KeyboardEvent) => { if (e.key === 'Escape') onClose() }

  const pickFromCandidate = (c: Candidate) => {
    onUseCandidate({
      product_code: c.target_product_code,
      product_name: c.target_product_name,
      unit: null,
      mrp: c.mrp,
      brand: c.brand,
      strength: c.strength,
      unit_of_strength: null,
      dosage_form: c.dosage_form,
      pack_size: null,
    })
  }

  return (
    <div className="pmx-drawer-wrap" role="dialog" aria-modal="true" aria-label="Match logic" onKeyDown={onKeyDown}>
      <div className="pmx-drawer-backdrop" onClick={onClose} />
      <aside className="pmx-drawer">
        <header className="pmx-drawer__head">
          <div className="min-w-0">
            <h5 className="pmx-modal__title"><i className="bi bi-diagram-3 me-2" aria-hidden="true" />How Matched</h5>
            <div className="pmx-modal__sub">{mapping.source_product_name}</div>
          </div>
          <button type="button" className="pmx-modal__close" aria-label="Close" onClick={onClose}>
            <i className="bi bi-x-lg" aria-hidden="true" />
          </button>
        </header>

        <div className="pmx-drawer__body">
          {loading && <div className="pmx-modal__hint">Loading match details…</div>}
          {error && <div className="pmx-modal__hint text-danger">{error}</div>}
          {!loading && !error && (
            <>
              <section className="pmx-drawer__section">
                <h6>Source</h6>
                <div className="pmx-kv">
                  <span>Original</span><span>{mapping.source_product_name} <span className="sx-dim">({mapping.source_product_code})</span></span>
                  <span>Normalized</span><span>{mapping.source_normalized_name || <span className="sx-dim">—</span>}</span>
                  <span>Parsed attrs</span>
                  <span>
                    {[mapping.brand, mapping.strength && `${mapping.strength}${mapping.unit ?? ''}`, mapping.dosage_form, mapping.pack_size]
                      .filter(Boolean).join(' · ') || <span className="sx-dim">—</span>}
                  </span>
                </div>
              </section>

              <section className="pmx-drawer__section">
                <h6>Match Result</h6>
                <div className="pmx-kv">
                  <span>Method</span><span>{mapping.match_method ?? <span className="sx-dim">Unmatched</span>}</span>
                  <span>Phase</span><span>{mapping.match_phase ?? <span className="sx-dim">—</span>}</span>
                  <span>Confidence</span><span><ConfidenceChip value={mapping.confidence} /></span>
                  <span>Current suggestion</span>
                  <span>{mapping.target_product_name
                    ? <ProductCell code={mapping.target_product_code} name={mapping.target_product_name} />
                    : <span className="sx-dim">No suggestion — needs manual selection</span>}</span>
                </div>
              </section>

              <section className="pmx-drawer__section">
                <h6>Candidates {detail && `(${detail.candidates.length})`}</h6>
                {!detail || detail.candidates.length === 0 ? (
                  <div className="pmx-modal__hint">No candidate products were scored for this item.</div>
                ) : (
                  <table className="sx-table pmx-drawer__table">
                    <thead>
                      <tr>
                        <th>Candidate</th>
                        <th className="sx-num">Name</th>
                        <th className="sx-num">Brand</th>
                        <th className="sx-num">Strength</th>
                        <th className="sx-num">Form</th>
                        <th className="sx-num">MRP</th>
                        <th className="sx-num">Total</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {detail.candidates
                        .slice()
                        .sort((a, b) => b.total_score - a.total_score)
                        .slice(0, 10)
                        .map((c, i) => {
                          const isCurrent = c.target_product_code === mapping.target_product_code
                          return (
                            <tr key={c.candidate_id} className={isCurrent ? 'sx-row--active' : ''}>
                              <td>
                                <div className="sx-rowlabel">
                                  <span className="sx-rowlabel__main">#{i + 1} {c.target_product_name}</span>
                                  <span className="sx-rowlabel__sub">
                                    Code {c.target_product_code}{isCurrent ? ' · current suggestion' : ''}
                                  </span>
                                </div>
                                {c.reason && <div className="sx-dim pmx-drawer__reason">{c.reason}</div>}
                              </td>
                              <td className="sx-num sx-dim">{c.name_score.toFixed(0)}</td>
                              <td className="sx-num sx-dim">{c.brand_score.toFixed(0)}</td>
                              <td className="sx-num sx-dim">{c.strength_score.toFixed(0)}</td>
                              <td className="sx-num sx-dim">{c.form_score.toFixed(0)}</td>
                              <td className="sx-num sx-dim"><Money value={c.mrp} /></td>
                              <td className="sx-num"><ConfidenceChip value={c.total_score} /></td>
                              <td className="sx-num">
                                <button
                                  type="button"
                                  className="sx-btn sx-btn--success sx-btn--sm"
                                  disabled={isCurrent}
                                  onClick={() => pickFromCandidate(c)}
                                  title="Use this candidate as the correct product"
                                >
                                  <i className="bi bi-check2" aria-hidden="true" />Use
                                </button>
                              </td>
                            </tr>
                          )
                        })}
                    </tbody>
                  </table>
                )}
              </section>
            </>
          )}
        </div>
      </aside>
    </div>
  )
}
