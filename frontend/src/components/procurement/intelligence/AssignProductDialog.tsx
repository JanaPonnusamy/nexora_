import { useCallback, useEffect, useState } from 'react'
import type { PiOfferRow, PiResolveStore } from '../../../types/intelligence'
import type { ProductSearchResult } from '../../../types/productMapping'
import { intelligenceService } from '../../../services/intelligenceService'
import { productMappingService } from '../../../services/productMappingService'

/**
 * Inline mapping for an unmapped supplier line — the buyer never leaves Product
 * Intelligence:
 *
 *     supplier product -> search the WAREHOUSE product -> the other stores are
 *     resolved automatically through the Common Product Mapping -> anything that
 *     did not resolve is picked by hand -> Save.
 *
 * The warehouse link is remembered by procurement (so the supplier's next import
 * still resolves), and each store link is written as a MANUAL/APPROVED edge in
 * the SAME dbo.product_mapping table the mapping module owns — no parallel
 * matching engine, and ProductCode is never used as a shared key.
 */
export function AssignProductDialog({
  tenantId,
  warehouseStoreId,
  warehouseName,
  row,
  actor,
  onClose,
  onSaved,
}: {
  tenantId: string
  warehouseStoreId: string
  warehouseName: string
  row: PiOfferRow
  actor: string | null
  onClose: () => void
  onSaved: (message: string) => void
}) {
  const [query, setQuery] = useState(row.supplier_product_name ?? '')
  const [hits, setHits] = useState<ProductSearchResult[]>([])
  const [searching, setSearching] = useState(false)
  const [picked, setPicked] = useState<ProductSearchResult | null>(null)
  const [resolved, setResolved] = useState<PiResolveStore[]>([])
  const [resolving, setResolving] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Which store is having its product picked by hand right now.
  const [manualStore, setManualStore] = useState<string | null>(null)
  const [manualQuery, setManualQuery] = useState('')
  const [manualHits, setManualHits] = useState<ProductSearchResult[]>([])

  const search = useCallback(
    (storeId: string, q: string, into: (r: ProductSearchResult[]) => void) => {
      if (q.trim().length < 2) { into([]); return }
      productMappingService.searchProducts(tenantId, storeId, q.trim(), 20)
        .then(into)
        .catch(() => into([]))
    },
    [tenantId],
  )

  // Warehouse product search (debounced — the buyer types fast).
  useEffect(() => {
    if (picked) return
    setSearching(true)
    const t = window.setTimeout(() => {
      search(warehouseStoreId, query, (r) => { setHits(r); setSearching(false) })
    }, 250)
    return () => { window.clearTimeout(t); setSearching(false) }
  }, [query, picked, warehouseStoreId, search])

  useEffect(() => {
    if (!manualStore) return
    const t = window.setTimeout(() => search(manualStore, manualQuery, setManualHits), 250)
    return () => window.clearTimeout(t)
  }, [manualStore, manualQuery, search])

  // Picking the warehouse product resolves every other store automatically.
  const pick = (p: ProductSearchResult) => {
    setPicked(p)
    setResolving(true)
    setError(null)
    intelligenceService.resolveAssignment(tenantId, warehouseStoreId, p.product_code)
      .then((r) => setResolved(r.stores))
      .catch((e) => setError(e instanceof Error ? e.message : 'Could not resolve the other stores'))
      .finally(() => setResolving(false))
  }

  const setStoreProduct = (storeId: string, p: ProductSearchResult) => {
    setResolved((cur) => cur.map((s) => s.store_id === storeId
      ? { ...s, product_code: p.product_code, product_name: p.product_name, auto: false }
      : s))
    setManualStore(null)
    setManualQuery('')
    setManualHits([])
  }

  const save = async () => {
    if (!picked) return
    setSaving(true)
    setError(null)
    try {
      const res = await intelligenceService.assign({
        tenant_id: tenantId,
        warehouse_store_id: warehouseStoreId,
        supplier_code: row.supplier_code,
        supplier_product_code: row.supplier_product_code ?? '',
        supplier_product_name: row.supplier_product_name,
        product_code: picked.product_code,
        store_assignments: resolved
          .filter((s) => s.product_code)
          .map((s) => ({ store_id: s.store_id, product_code: s.product_code })),
        actor,
      })
      onSaved(
        `Mapped to ${res.product_name ?? res.product_code}` +
        (res.mapped_stores.length ? ` · ${res.mapped_stores.length} more store${res.mapped_stores.length === 1 ? '' : 's'} linked` : ''),
      )
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Assignment failed')
      setSaving(false)
    }
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="pi-modal__back" onClick={onClose}>
      <div className="pi-modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Assign supplier product">
        <div className="pi-modal__head">
          <div>
            <div className="pi-modal__title">{row.supplier_product_name ?? '—'}</div>
            <div className="pi-modal__sub">
              Supplier {row.supplier_code} · {row.supplier_product_code ?? '—'}
            </div>
          </div>
          <button type="button" className="pm-btn pm-btn--ghost" onClick={onClose}>
            <i className="bi bi-x-lg" />
          </button>
        </div>

        <div className="pi-modal__body">
          <div className="pi-modal__step">1 · {warehouseName} product</div>
          {picked ? (
            <div className="pi-picked">
              <span><b>{picked.product_name}</b> · code {picked.product_code}</span>
              <button type="button" className="pm-btn pm-btn--ghost" onClick={() => { setPicked(null); setResolved([]) }}>
                Change
              </button>
            </div>
          ) : (
            <>
              <span className="sx-search pi-modal__search">
                <i className="bi bi-search" aria-hidden="true" />
                <input
                  autoFocus
                  type="search"
                  value={query}
                  placeholder="Search the warehouse catalogue…"
                  onChange={(e) => setQuery(e.target.value)}
                />
              </span>
              <div className="pi-hits">
                {hits.map((p) => (
                  <button key={p.product_code} type="button" className="pi-hit" onClick={() => pick(p)}>
                    <b>{p.product_name}</b>
                    <span>{p.product_code}{p.pack_size ? ` · ${p.pack_size}` : ''}</span>
                  </button>
                ))}
                {!searching && query.trim().length >= 2 && hits.length === 0 && (
                  <div className="pi-hits__none">No match in the warehouse catalogue.</div>
                )}
              </div>
            </>
          )}

          {picked && (
            <>
              <div className="pi-modal__step">2 · Other stores {resolving && <i className="bi bi-hourglass-split" />}</div>
              <div className="pi-storelinks">
                {resolved.map((s) => (
                  <div className="pi-storelink" key={s.store_id}>
                    <span className="pi-storelink__code">{s.store_code ?? '—'}</span>
                    {manualStore === s.store_id ? (
                      <div className="pi-storelink__pick">
                        <span className="sx-search">
                          <i className="bi bi-search" aria-hidden="true" />
                          <input
                            autoFocus
                            type="search"
                            value={manualQuery}
                            placeholder={`Search ${s.store_code ?? 'store'}…`}
                            onChange={(e) => setManualQuery(e.target.value)}
                          />
                        </span>
                        <div className="pi-hits pi-hits--inline">
                          {manualHits.map((p) => (
                            <button key={p.product_code} type="button" className="pi-hit" onClick={() => setStoreProduct(s.store_id, p)}>
                              <b>{p.product_name}</b><span>{p.product_code}</span>
                            </button>
                          ))}
                        </div>
                      </div>
                    ) : (
                      <>
                        <span className="pi-storelink__prod">
                          {s.product_code
                            ? <>{s.product_name ?? s.product_code} <em>{s.auto ? 'auto' : 'manual'}</em></>
                            : <em className="pi-storelink__miss">not mapped</em>}
                        </span>
                        <button
                          type="button"
                          className="pm-btn pm-btn--ghost pi-storelink__btn"
                          onClick={() => { setManualStore(s.store_id); setManualQuery(picked.product_name) }}
                        >
                          {s.product_code ? 'Change' : 'Assign'}
                        </button>
                      </>
                    )}
                  </div>
                ))}
              </div>
            </>
          )}

          {error && <div className="pi-modal__err"><i className="bi bi-exclamation-triangle-fill" /> {error}</div>}
        </div>

        <div className="pi-modal__foot">
          <button type="button" className="pm-btn pm-btn--ghost" onClick={onClose}>Cancel</button>
          <button type="button" className="pm-btn pm-btn--import" disabled={!picked || saving} onClick={save}>
            {saving ? 'Saving…' : 'Save mapping'}
          </button>
        </div>
      </div>
    </div>
  )
}
