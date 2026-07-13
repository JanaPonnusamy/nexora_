import { useCallback, useEffect, useMemo, useState } from 'react'
import type { SupplierRow, SupplierSettingsRow, WorkspaceItem } from '../../types/procurement'
import { procurementService } from '../../services/procurementService'
import { computeRankAssignment } from './purchaseValue'
import { num } from '../stock/format'

/**
 * Supplier Rank & Settings — a live "what would Auto Assign actually do"
 * table, not just a settings form. Shows every supplier relevant to the
 * OPEN refresh (present in its recommendations, not the whole supplier
 * master), each with an editable Rank / Auto Assign / Min Products, and a
 * live "Possible Products" count computed via computeRankAssignment (the
 * SAME function Rank-mode Auto Assign commits with) — so setting rank 1 on
 * one supplier immediately shows the shared products it claims disappearing
 * from every lower-priority supplier's count, without a round trip.
 */
export function SupplierRankPanel({
  tenantId,
  storeId,
  eligibleItems,
  recommendations,
  nameOf,
  notify,
}: {
  tenantId: string
  storeId: string
  /** Products currently eligible for Auto Assign (already filtered — see
   *  eligibleForAutoAssign). */
  eligibleItems: WorkspaceItem[]
  recommendations: Record<string, SupplierRow[]>
  nameOf: (code: string) => string
  notify: (kind: 'success' | 'danger', text: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [settings, setSettings] = useState<SupplierSettingsRow[]>([])
  const [loading, setLoading] = useState(false)
  const [rankEdits, setRankEdits] = useState<Record<string, string>>({})
  const [minEdits, setMinEdits] = useState<Record<string, string>>({})
  const [savingCode, setSavingCode] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!tenantId || !storeId) return
    setLoading(true)
    try {
      const rows = await procurementService.supplierSettings(tenantId, storeId)
      setSettings(rows)
      setRankEdits(Object.fromEntries(rows.map((r) => [r.supplier_code, r.export_rank != null ? String(r.export_rank) : ''])))
      setMinEdits(Object.fromEntries(rows.map((r) => [r.supplier_code, String(r.min_products)])))
    } catch (e) {
      notify('danger', e instanceof Error ? e.message : 'Failed to load supplier settings')
    } finally {
      setLoading(false)
    }
  }, [tenantId, storeId, notify])

  useEffect(() => {
    if (open) load()
  }, [open, load])

  // Only suppliers this refresh's eligible products could actually go to —
  // "today's order available suppliers only", not the whole supplier master.
  const relevantCodes = useMemo(() => {
    const s = new Set<string>()
    eligibleItems.forEach((it) => (recommendations[it.order_item_id] ?? []).forEach((r) => s.add(r.supplier_code)))
    return s
  }, [eligibleItems, recommendations])

  const visible = useMemo(
    () => settings.filter((s) => relevantCodes.has(s.supplier_code)),
    [settings, relevantCodes],
  )

  const autoAssignMap = useMemo(
    () => Object.fromEntries(visible.map((s) => [s.supplier_code, s.auto_assign])),
    [visible],
  )

  // Live claim simulation — recomputes instantly on every rank/auto-assign
  // edit (client-side, no round trip). Uses the DRAFT rank edits (not yet
  // saved) so the count reacts as the buyer types, not only after blur.
  const draftRanks = useMemo(() => {
    const out: Record<string, number | null> = {}
    visible.forEach((s) => {
      const raw = rankEdits[s.supplier_code]
      const n = raw != null && raw !== '' ? Number(raw) : null
      out[s.supplier_code] = n != null && !Number.isNaN(n) && n > 0 ? n : null
    })
    return out
  }, [visible, rankEdits])

  const rankResult = useMemo(
    () => computeRankAssignment(eligibleItems, recommendations, draftRanks, autoAssignMap),
    [eligibleItems, recommendations, draftRanks, autoAssignMap],
  )

  const orderedVisible = useMemo(() => {
    const rank = (code: string) => rankResult.order.indexOf(code)
    return [...visible].sort((a, b) => rank(a.supplier_code) - rank(b.supplier_code))
  }, [visible, rankResult])

  const saveRank = async (code: string) => {
    const raw = rankEdits[code]
    const n = raw === '' ? 0 : Number(raw)
    if (Number.isNaN(n) || n < 0) return notify('danger', 'Rank must be a positive number (blank = unranked)')
    setSavingCode(code)
    try {
      await procurementService.updateSupplierSettings(tenantId, storeId, code, { export_rank: n })
      setSettings((rows) => rows.map((r) => (r.supplier_code === code ? { ...r, export_rank: n > 0 ? n : null } : r)))
    } catch (e) {
      notify('danger', e instanceof Error ? e.message : 'Failed to save rank')
    } finally {
      setSavingCode(null)
    }
  }

  const saveMinProducts = async (code: string) => {
    const n = Number(minEdits[code])
    if (Number.isNaN(n) || n < 1) return notify('danger', 'Minimum products must be at least 1')
    setSavingCode(code)
    try {
      await procurementService.updateSupplierSettings(tenantId, storeId, code, { min_products: n })
      setSettings((rows) => rows.map((r) => (r.supplier_code === code ? { ...r, min_products: n } : r)))
    } catch (e) {
      notify('danger', e instanceof Error ? e.message : 'Failed to save minimum products')
    } finally {
      setSavingCode(null)
    }
  }

  const toggleAutoAssign = async (code: string, current: boolean) => {
    setSettings((rows) => rows.map((r) => (r.supplier_code === code ? { ...r, auto_assign: !current } : r))) // optimistic
    try {
      await procurementService.updateSupplierSettings(tenantId, storeId, code, { auto_assign: !current })
    } catch (e) {
      setSettings((rows) => rows.map((r) => (r.supplier_code === code ? { ...r, auto_assign: current } : r))) // revert
      notify('danger', e instanceof Error ? e.message : 'Failed to update setting')
    }
  }

  const rankedCount = visible.filter((s) => s.export_rank != null).length

  return (
    <div className="pm-opt__settings pm-rankpanel">
      <button className="pm-sq__toggle pm-opt__settingstoggle" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <i className={`bi ${open ? 'bi-chevron-down' : 'bi-chevron-right'}`} />
        <i className="bi bi-sort-numeric-down" /> Supplier Rank &amp; Settings
        {visible.length > 0 && (
          <span className="pm-sq__sum">{rankedCount} of {visible.length} suppliers ranked</span>
        )}
      </button>
      {open && (
        loading ? (
          <div className="pm-sq__hint">Loading supplier settings…</div>
        ) : visible.length === 0 ? (
          <div className="pm-sq__hint">No suppliers have purchase history for the currently eligible products.</div>
        ) : (
          <>
            <div className="pm-rank__head">
              <span className="pm-rank__headcol pm-rank__headcol--rank">Rank</span>
              <span className="pm-rank__headcol pm-rank__headcol--name">Supplier</span>
              <span className="pm-rank__headcol">Auto Assign</span>
              <span className="pm-rank__headcol">Min Products</span>
              <span className="pm-rank__headcol">Possible</span>
            </div>
            <div className="pm-rank__list">
              {orderedVisible.map((s) => {
                const code = s.supplier_code
                const possible = rankResult.assignedItems[code]?.length ?? 0
                const gap = possible < s.min_products
                return (
                  <div key={code} className={`pm-rankcard${s.auto_assign ? '' : ' pm-rankcard--off'}`}>
                    <input
                      className="pm-qty pm-opt__mininp pm-rankcard__rank"
                      value={rankEdits[code] ?? ''}
                      inputMode="numeric"
                      placeholder="—"
                      disabled={savingCode === code}
                      onChange={(e) => setRankEdits((d) => ({ ...d, [code]: e.target.value.replace(/[^\d]/g, '') }))}
                      onKeyDown={(e) => e.key === 'Enter' && saveRank(code)}
                      onBlur={() => { if (Number(rankEdits[code] || 0) !== (s.export_rank ?? 0)) saveRank(code) }}
                      aria-label={`Export rank for ${nameOf(code)}`}
                    />
                    <div className="pm-rankcard__name">
                      <div className="pm-prod__name">{nameOf(code)}</div>
                      <div className="pm-prod__meta">{code}</div>
                    </div>
                    <label className="pm-chk pm-rankcard__auto">
                      <input type="checkbox" checked={s.auto_assign} onChange={() => toggleAutoAssign(code, s.auto_assign)} />
                      {s.auto_assign ? 'On' : 'Off'}
                    </label>
                    <span className="pm-rankcard__stat">
                      <input
                        className="pm-qty pm-opt__mininp"
                        value={minEdits[code] ?? ''}
                        inputMode="numeric"
                        disabled={savingCode === code}
                        onChange={(e) => setMinEdits((d) => ({ ...d, [code]: e.target.value.replace(/[^\d]/g, '') }))}
                        onKeyDown={(e) => e.key === 'Enter' && saveMinProducts(code)}
                        onBlur={() => { if (Number(minEdits[code] || 0) !== s.min_products) saveMinProducts(code) }}
                        aria-label={`Minimum products for ${nameOf(code)}`}
                      />
                    </span>
                    <span className="pm-rankcard__stat">
                      <b className={gap ? 'pm-opt__gap' : 'pm-opt__ok'}>{num(possible)}</b>
                    </span>
                  </div>
                )
              })}
            </div>
          </>
        )
      )}
    </div>
  )
}
