import { useCallback, useEffect, useMemo, useState } from 'react'
import { procurementService } from '../../services/procurementService'
import type { OptimizationResult, OptimizationSupplier, SupplierMinOrderConfig } from '../../types/procurement'
import { money, num } from '../stock/format'

/**
 * Supplier Optimization — the stage between Auto Supplier Assignment and Export.
 *
 * For every supplier below its Minimum Order Value it shows the lowest-value
 * combination of products (from other suppliers who also supply them) that
 * lifts it to the minimum, and lets the buyer Accept / Reject each suggestion,
 * Accept-All / Reject-All, edit a supplier's minimum inline, or Manual Move a
 * specific product. Totals update on every applied move (the parent reloads the
 * workspace + Supplier Queue). Reuses the assignment change path + export rules;
 * only suppliers reaching their minimum become exportable.
 */

const STATUS_META: Record<OptimizationSupplier['status'], { label: string; cls: string }> = {
  ok: { label: 'Ready', cls: 'pm-optstat--ok' },
  ready: { label: 'Fix Ready', cls: 'pm-optstat--ready' },
  short: { label: 'Needs Optimization', cls: 'pm-optstat--short' },
  no_solution: { label: 'Needs Optimization', cls: 'pm-optstat--none' },
}

export function SupplierOptimizationPanel({
  tenantId,
  refreshId,
  storeId,
  actingUser,
  nameOf,
  notify,
  onApplied,
}: {
  tenantId: string
  refreshId: string
  storeId: string
  actingUser: string
  nameOf: (code: string) => string
  notify: (kind: 'success' | 'danger', text: string) => void
  onApplied: () => void
}) {
  const [open, setOpen] = useState(false)
  const [result, setResult] = useState<OptimizationResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const [minEdits, setMinEdits] = useState<Record<string, string>>({})
  // §10/§11 — per-supplier opt-in flag; a configured min_order_value alone no
  // longer enrolls a supplier in Optimization.
  const [considerFlags, setConsiderFlags] = useState<Record<string, boolean>>({})
  const [settingsOpen, setSettingsOpen] = useState(false)
  // Locally rejected suggestion lines (assignment_id) — excluded from Accept.
  const [rejected, setRejected] = useState<Set<string>>(new Set())
  // Manual-move draft: supplier_code -> chosen assignment_id.
  const [manualPick, setManualPick] = useState<Record<string, string>>({})

  const load = useCallback(async () => {
    if (!tenantId || !refreshId) return
    setLoading(true)
    try {
      const [res, config] = await Promise.all([
        procurementService.optimization(tenantId, refreshId),
        storeId
          ? procurementService.minOrderConfig(tenantId, storeId)
          : Promise.resolve<Record<string, SupplierMinOrderConfig>>({}),
      ])
      setResult(res)
      // Seed from the raw config (not res.suppliers[].min_value, which analyze()
      // now reports as the EFFECTIVE minimum — 0 for a not-considered supplier —
      // so the Settings panel must show what's actually configured, §10/§11).
      setMinEdits(
        Object.fromEntries(
          res.suppliers.map((s) => [s.supplier_code, String(config[s.supplier_code]?.min_order_value || s.min_value || '')]),
        ),
      )
      setConsiderFlags(
        Object.fromEntries(res.suppliers.map((s) => [s.supplier_code, config[s.supplier_code]?.consider_minimum_order ?? false])),
      )
      setRejected(new Set())
      setManualPick({})
      setOpen(true)
    } catch (e) {
      notify('danger', e instanceof Error ? e.message : 'Optimization failed')
    } finally {
      setLoading(false)
    }
  }, [tenantId, refreshId, storeId, notify])

  const toggleConsider = async (code: string) => {
    const next = !considerFlags[code]
    setConsiderFlags((d) => ({ ...d, [code]: next })) // optimistic
    try {
      await procurementService.setConsiderMinimumOrder(tenantId, code, storeId, next, actingUser || null)
      await load()
      notify('success', `${nameOf(code)} ${next ? 'now participates in' : 'excluded from'} Optimization`)
    } catch (e) {
      setConsiderFlags((d) => ({ ...d, [code]: !next })) // revert
      notify('danger', e instanceof Error ? e.message : 'Failed to update setting')
    }
  }

  // Reset when the refresh changes so stale suggestions never linger.
  useEffect(() => {
    setResult(null)
    setOpen(false)
  }, [refreshId])

  const belowMin = useMemo(
    () => (result?.suppliers ?? []).filter((s) => s.status !== 'ok'),
    [result],
  )
  const okCount = (result?.suppliers.length ?? 0) - belowMin.length

  const liveSuggestions = (s: OptimizationSupplier) =>
    s.suggestions.filter((m) => !rejected.has(m.assignment_id))

  const saveMin = async (code: string) => {
    const v = Number(minEdits[code])
    if (Number.isNaN(v) || v < 0) return notify('danger', 'Enter a valid minimum (≥ 0)')
    try {
      await procurementService.setMinOrder(tenantId, code, storeId, v, actingUser || null)
      await load()
      notify('success', `Minimum for ${nameOf(code)} set to ${money(v)}`)
    } catch (e) {
      notify('danger', e instanceof Error ? e.message : 'Failed to save minimum')
    }
  }

  const applyMoves = async (moves: { assignment_id: string; to_supplier: string }[], label: string) => {
    if (moves.length === 0) return notify('danger', 'No suggestions to apply')
    setBusy(label)
    try {
      const res = await procurementService.applyOptimization(tenantId, refreshId, moves, actingUser || null, 'auto')
      notify(
        res.skipped ? 'danger' : 'success',
        `Moved ${res.moved} product${res.moved === 1 ? '' : 's'}${res.skipped ? `, ${res.skipped} skipped` : ''}`,
      )
      onApplied()
      await load()
    } catch (e) {
      notify('danger', e instanceof Error ? e.message : 'Failed to apply moves')
    } finally {
      setBusy(null)
    }
  }

  const acceptSupplier = (s: OptimizationSupplier) =>
    applyMoves(
      liveSuggestions(s).map((m) => ({ assignment_id: m.assignment_id, to_supplier: m.to_supplier })),
      s.supplier_code,
    )

  const acceptAll = () =>
    applyMoves(
      belowMin.flatMap((s) =>
        liveSuggestions(s).map((m) => ({ assignment_id: m.assignment_id, to_supplier: m.to_supplier })),
      ),
      '__all__',
    )

  const rejectSupplier = (s: OptimizationSupplier) =>
    setRejected((prev) => {
      const next = new Set(prev)
      s.suggestions.forEach((m) => next.add(m.assignment_id))
      return next
    })

  const rejectAll = () =>
    setRejected(new Set(belowMin.flatMap((s) => s.suggestions.map((m) => m.assignment_id))))

  const manualMove = async (s: OptimizationSupplier) => {
    const aid = manualPick[s.supplier_code]
    if (!aid) return notify('danger', 'Pick a product to move')
    setBusy(`manual-${s.supplier_code}`)
    try {
      await procurementService.manualMove(tenantId, refreshId, aid, s.supplier_code, actingUser || null)
      notify('success', `Moved product to ${nameOf(s.supplier_code)}`)
      onApplied()
      await load()
    } catch (e) {
      notify('danger', e instanceof Error ? e.message : 'Manual move failed')
    } finally {
      setBusy(null)
    }
  }

  const projectedOf = (s: OptimizationSupplier) =>
    s.current_value + liveSuggestions(s).reduce((a, m) => a + m.value, 0)
  const totalPotential = belowMin.reduce((a, s) => a + liveSuggestions(s).reduce((b, m) => b + m.value, 0), 0)
  const totalMoves = belowMin.reduce((a, s) => a + liveSuggestions(s).length, 0)
  const fixable = belowMin.filter((s) => liveSuggestions(s).length > 0 && projectedOf(s) >= s.min_value).length
  const anySuggestions = totalMoves > 0

  return (
    <section className="pm-sq pm-opt" aria-label="Supplier Optimization">
      <header className="pm-sq__head">
        <button className="pm-sq__toggle" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
          <i className={`bi ${open ? 'bi-chevron-down' : 'bi-chevron-right'}`} />
          <i className="bi bi-sliders" /> Supplier Optimization
          {result && (
            <span className="pm-sq__sum">
              {belowMin.length} below minimum · {okCount} ready · potential {money(totalPotential)}
            </span>
          )}
        </button>
        <div className="pm-sq__actions">
          <button className="pm-btn pm-btn--ghost" onClick={load} disabled={loading}>
            <i className="bi bi-arrow-repeat" /> {loading ? 'Optimizing…' : result ? 'Re-optimize' : 'Optimize'}
          </button>
          {result && belowMin.length > 0 && (
            <>
              <button className="pm-btn pm-btn--ghost" onClick={rejectAll} disabled={!anySuggestions}>Reject All</button>
              <button className="pm-btn pm-btn--primary" onClick={acceptAll} disabled={busy != null || !anySuggestions}>
                <i className="bi bi-check2-all" /> Accept All Suggestions
              </button>
            </>
          )}
        </div>
      </header>

      {open && (
        <div className="pm-sq__body">
          {result && result.suppliers.length > 0 && (
            <div className="pm-opt__settings">
              <button className="pm-sq__toggle pm-opt__settingstoggle" onClick={() => setSettingsOpen((o) => !o)} aria-expanded={settingsOpen}>
                <i className={`bi ${settingsOpen ? 'bi-chevron-down' : 'bi-chevron-right'}`} />
                Minimum Order Settings
                <span className="pm-sq__sum">
                  {Object.values(considerFlags).filter(Boolean).length} of {result.suppliers.length} suppliers opted in
                </span>
              </button>
              {settingsOpen && (
                <table className="pm-opt__table pm-opt__settingstable">
                  <thead>
                    <tr>
                      <th>Supplier</th>
                      <th className="sx-num">Minimum Order Value</th>
                      <th>Consider in Optimization</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.suppliers.map((s) => (
                      <tr key={s.supplier_code}>
                        <td>
                          <div className="pm-prod__name">{nameOf(s.supplier_code)}</div>
                          <div className="pm-prod__meta">{s.supplier_code}</div>
                        </td>
                        <td className="sx-num">
                          <input
                            className="pm-qty pm-opt__mininp"
                            value={minEdits[s.supplier_code] ?? ''}
                            inputMode="numeric"
                            onChange={(e) => setMinEdits((d) => ({ ...d, [s.supplier_code]: e.target.value }))}
                            onKeyDown={(e) => e.key === 'Enter' && saveMin(s.supplier_code)}
                            onBlur={() => {
                              if (Number(minEdits[s.supplier_code]) !== s.min_value) saveMin(s.supplier_code)
                            }}
                            aria-label={`Minimum order value for ${s.supplier_code}`}
                          />
                        </td>
                        <td>
                          <label className="pm-chk">
                            <input
                              type="checkbox"
                              checked={considerFlags[s.supplier_code] ?? false}
                              onChange={() => toggleConsider(s.supplier_code)}
                            />
                            {considerFlags[s.supplier_code] ? 'Considered' : 'Ignored'}
                          </label>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}
          {!result ? (
            <div className="pm-sq__hint">Run Optimize to check which suppliers are below their Minimum Order Value.</div>
          ) : belowMin.length === 0 ? (
            <div className="pm-sq__hint">
              <i className="bi bi-check2-circle me-1" /> All {result.suppliers.length} suppliers meet their Minimum Order Value.
            </div>
          ) : (
            <div className="pm-opt__tablewrap">
              <div className="pm-opt__tiles">
                <span className="pm-opt__tile"><b>{num(belowMin.length)}</b><span>Below Minimum</span></span>
                <span className="pm-opt__tile pm-opt__tile--ok"><b>{num(fixable)}</b><span>Fix Ready</span></span>
                <span className="pm-opt__tile"><b>{num(totalMoves)}</b><span>Suggested Moves</span></span>
                <span className="pm-opt__tile"><b>{money(totalPotential)}</b><span>Added Value</span></span>
              </div>
              <table className="pm-opt__table">
                <thead>
                  <tr>
                    <th>Supplier</th>
                    <th className="sx-num">Current Value</th>
                    <th className="sx-num">Min Order</th>
                    <th className="sx-num">Remaining Gap</th>
                    <th className="sx-num">Moves</th>
                    <th>Suggested Move</th>
                    <th className="sx-num">Projected</th>
                    <th>Status</th>
                    <th className="pm-opt__act">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {belowMin.map((s) => {
                    const st = STATUS_META[s.status]
                    const sugg = liveSuggestions(s)
                    const projected = s.current_value + sugg.reduce((a, m) => a + m.value, 0)
                    const otherMovable = (s.movable ?? []).filter(
                      (m) => !sugg.some((x) => x.assignment_id === m.assignment_id),
                    )
                    return (
                      <tr key={s.supplier_code}>
                        <td>
                          <div className="pm-prod__name">{nameOf(s.supplier_code)}</div>
                          <div className="pm-prod__meta">{s.supplier_code} · {num(s.current_products)} products</div>
                        </td>
                        <td className="sx-num">{money(s.current_value)}</td>
                        <td className="sx-num">
                          <span className="pm-opt__min">
                            <input
                              className="pm-qty pm-opt__mininp"
                              value={minEdits[s.supplier_code] ?? ''}
                              inputMode="numeric"
                              onChange={(e) => setMinEdits((d) => ({ ...d, [s.supplier_code]: e.target.value }))}
                              onKeyDown={(e) => e.key === 'Enter' && saveMin(s.supplier_code)}
                              onBlur={() => {
                                if (Number(minEdits[s.supplier_code]) !== s.min_value) saveMin(s.supplier_code)
                              }}
                              aria-label={`Minimum order value for ${s.supplier_code}`}
                            />
                          </span>
                        </td>
                        <td className="sx-num pm-opt__gap">{money(s.gap)}</td>
                        <td className="sx-num"><b>{num(sugg.length)}</b></td>
                        <td>
                          {sugg.length === 0 ? (
                            <span className="sx-dim">{s.status === 'no_solution' ? 'No eligible products' : 'Rejected'}</span>
                          ) : (
                            <div className="pm-opt__chips">
                              {sugg.map((m) => (
                                <span key={m.assignment_id} className="pm-opt__chip">
                                  {m.product_name ?? m.product_code} {money(m.value)}
                                  <span className="pm-opt__chipfrom">← {nameOf(m.from_supplier)}</span>
                                </span>
                              ))}
                            </div>
                          )}
                        </td>
                        <td className="sx-num">
                          <b className={projected >= s.min_value ? 'pm-opt__ok' : ''}>{money(projected)}</b>
                        </td>
                        <td>
                          {sugg.length > 0 && projected >= s.min_value ? (
                            <span className="pm-optstat pm-optstat--ready">Fix Ready</span>
                          ) : (
                            <span className={`pm-optstat ${st.cls}`}>Needs Optimization</span>
                          )}
                        </td>
                        <td className="pm-opt__act">
                          <div className="pm-opt__btns">
                            <button
                              className="pm-btn pm-btn--success pm-btn--sm"
                              onClick={() => acceptSupplier(s)}
                              disabled={busy != null || sugg.length === 0}
                            >
                              Accept
                            </button>
                            <button
                              className="pm-btn pm-btn--ghost pm-btn--sm"
                              onClick={() => rejectSupplier(s)}
                              disabled={sugg.length === 0}
                            >
                              Reject
                            </button>
                          </div>
                          {otherMovable.length > 0 && (
                            <div className="pm-opt__manual">
                              <select
                                className="sx-select pm-opt__manualsel"
                                value={manualPick[s.supplier_code] ?? ''}
                                onChange={(e) => setManualPick((d) => ({ ...d, [s.supplier_code]: e.target.value }))}
                                aria-label="Choose a product to move manually"
                              >
                                <option value="">Manual move…</option>
                                {otherMovable.map((m) => (
                                  <option key={m.assignment_id} value={m.assignment_id}>
                                    {(m.product_name ?? m.product_code) + ` (${money(m.value)}) ← ${nameOf(m.from_supplier)}`}
                                  </option>
                                ))}
                              </select>
                              <button
                                className="pm-btn pm-btn--ghost pm-btn--sm"
                                onClick={() => manualMove(s)}
                                disabled={busy != null || !manualPick[s.supplier_code]}
                              >
                                Move →
                              </button>
                            </div>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
              <p className="pm-opt__note">
                <i className="bi bi-info-circle me-1" />
                Only suppliers reaching their Minimum Order Value become exportable; the rest stay pending. Every move is audited.
              </p>
            </div>
          )}
        </div>
      )}
    </section>
  )
}
