import { useEffect, useMemo, useState } from 'react'
import { PageHeader } from '../../components/common/PageHeader'
import { EmptyState } from '../../components/common/EmptyState'
import { ErrorState } from '../../components/common/ErrorState'
import { FilterBar } from '../../design-system/components/FilterBar'
import { tenantService } from '../../services/tenantService'
import { storeService } from '../../services/storeService'
import { saleAnalysisService } from '../../services/saleAnalysisService'
import type {
  SaleAnalysisResult,
  SaleGroupSummary,
  SaleProductOption,
  SaleSupplierOption,
  SaleWindow,
} from '../../types/saleAnalysis'
import type { ExpiryColumn } from '../../types/expiryReport'
import type { Tenant } from '../../types/tenant'
import type { Store } from '../../types/store'
import { money, num } from '../../components/stock/format'
import { exportExpiryExcel } from '../expiry-report/exportExpiryExcel'
import '../reports.css'
import './sale-analysis.css'

const WINDOWS: { key: SaleWindow; label: string }[] = [
  { key: 'month', label: 'This Month' },
  { key: 'last30', label: 'Last 30 Days' },
  { key: 'range', label: 'Custom Range' },
]

/** Cover Days is a plain decimal (no currency); everything else follows the
 *  column's declared format. */
function cell(value: unknown, col: ExpiryColumn): string {
  if (col.key === 'CoverDays') {
    if (value === null || value === undefined || value === '') return '∞'
    return Number(value).toFixed(1)
  }
  if (value === null || value === undefined || value === '') return col.format === 'money' ? '—' : ''
  if (col.format === 'money') return money(Number(value))
  if (col.format === 'int') return num(Number(value))
  return String(value)
}

export default function SaleAnalysisPage() {
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [tenantId, setTenantId] = useState('')
  const [stores, setStores] = useState<Store[]>([])
  const [storeId, setStoreId] = useState('')

  const [window, setWindow] = useState<SaleWindow>('month')
  const [fromDate, setFromDate] = useState('')
  const [toDate, setToDate] = useState('')
  const [targetDays, setTargetDays] = useState(30)

  const [groups, setGroups] = useState<SaleGroupSummary[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())

  // Builder state
  const [builderOpen, setBuilderOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [groupName, setGroupName] = useState('')
  const [query, setQuery] = useState('')
  const [supplierFilter, setSupplierFilter] = useState('')
  const [supplierOptions, setSupplierOptions] = useState<SaleSupplierOption[]>([])
  const [searchResults, setSearchResults] = useState<SaleProductOption[]>([])
  const [picked, setPicked] = useState<Map<string, SaleProductOption>>(new Map())
  const [saving, setSaving] = useState(false)
  const [addingAll, setAddingAll] = useState(false)

  const [result, setResult] = useState<SaleAnalysisResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  // --- scope bootstrap ----------------------------------------------------
  useEffect(() => {
    tenantService.list().then((rows) => {
      const active = rows.filter((t) => t.is_active)
      setTenants(active)
      if (active.length) setTenantId((cur) => cur || active[0].tenant_id)
    }).catch(() => setTenants([]))
    storeService.list().then(setStores).catch(() => setStores([]))
  }, [])

  const tenantStores = useMemo(
    () => stores.filter((s) => s.tenant_id === tenantId && s.is_active),
    [stores, tenantId],
  )
  useEffect(() => {
    setStoreId((cur) => (tenantStores.some((s) => s.store_id === cur) ? cur : tenantStores[0]?.store_id ?? ''))
  }, [tenantStores])

  // --- saved groups -------------------------------------------------------
  const reloadGroups = () => {
    if (!tenantId) return
    saleAnalysisService.listGroups(tenantId).then(setGroups).catch(() => setGroups([]))
  }
  useEffect(() => {
    reloadGroups()
    setSelected(new Set())
    setResult(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId])

  // --- builder: supplier options -----------------------------------------
  useEffect(() => {
    if (!builderOpen || !tenantId || !storeId) return
    let live = true
    saleAnalysisService.suppliers(tenantId, storeId, '')
      .then((r) => { if (live) setSupplierOptions(r) })
      .catch(() => { if (live) setSupplierOptions([]) })
    return () => { live = false }
  }, [builderOpen, tenantId, storeId])

  // --- builder: product search (debounced) --------------------------------
  useEffect(() => {
    if (!builderOpen || !tenantId || !storeId) return
    if (!query.trim() && !supplierFilter) { setSearchResults([]); return }
    let live = true
    const t = setTimeout(() => {
      saleAnalysisService.products(tenantId, storeId, query.trim(), supplierFilter || undefined)
        .then((r) => { if (live) setSearchResults(r) })
        .catch(() => { if (live) setSearchResults([]) })
    }, 250)
    return () => { live = false; clearTimeout(t) }
  }, [builderOpen, tenantId, storeId, query, supplierFilter])

  // --- report run ---------------------------------------------------------
  const runReport = () => {
    if (!tenantId || !storeId || selected.size === 0) return
    if (window === 'range' && (!fromDate || !toDate)) {
      setError('Pick both From and To dates for a custom range.')
      return
    }
    setLoading(true)
    setError(null)
    saleAnalysisService
      .report(tenantId, storeId, {
        groupIds: [...selected],
        window,
        from: window === 'range' ? fromDate : undefined,
        to: window === 'range' ? toDate : undefined,
        targetDays: Number(targetDays) || 30,
      })
      .then((r) => { setResult(r); setExpanded(new Set(r.groups.map((g) => g.group_name))) })
      .catch((err) => { setResult(null); setError(err instanceof Error ? err.message : 'Failed to load') })
      .finally(() => setLoading(false))
  }

  // --- builder actions ----------------------------------------------------
  const openNewBuilder = () => {
    setBuilderOpen(true); setEditingId(null); setGroupName('')
    setPicked(new Map()); setQuery(''); setSupplierFilter(''); setSearchResults([])
  }
  const openEditBuilder = (g: SaleGroupSummary) => {
    setBuilderOpen(true); setEditingId(g.group_id); setGroupName(g.group_name)
    setQuery(''); setSupplierFilter(''); setSearchResults([])
    saleAnalysisService.getGroup(tenantId, g.group_id).then((detail) => {
      // Rehydrate chips from the saved product names (keyed by name).
      const map = new Map<string, SaleProductOption>()
      detail.product_names.forEach((name) =>
        map.set(name, { product_code: name, product_name: name, supplier_code: null, supplier_name: null, current_stock: null, mrp: null }),
      )
      setPicked(map)
    }).catch(() => { /* keep empty */ })
  }
  const closeBuilder = () => { setBuilderOpen(false); setEditingId(null) }

  // Groups are keyed by product NAME (codes differ per store), so the builder
  // dedupes/keys picked products by their name.
  const addProduct = (p: SaleProductOption) => {
    setPicked((cur) => new Map(cur).set(p.product_name, p))
  }
  const removeProduct = (name: string) => {
    setPicked((cur) => { const m = new Map(cur); m.delete(name); return m })
  }
  // One click → pull every product matching the current supplier/search (not just
  // the 50 previewed) and add them all to the group. This is the "friends group"
  // fast path: pick a supplier, click Add all, name it, Save.
  const addAllProducts = () => {
    if (!tenantId || !storeId) return
    if (!query.trim() && !supplierFilter) return
    setAddingAll(true)
    saleAnalysisService.products(tenantId, storeId, query.trim(), supplierFilter || undefined, 2000)
      .then((all) => setPicked((cur) => {
        const m = new Map(cur)
        all.forEach((p) => m.set(p.product_name, p))
        return m
      }))
      .catch((err) => setError(err instanceof Error ? err.message : 'Add all failed'))
      .finally(() => setAddingAll(false))
  }
  const clearPicked = () => setPicked(new Map())

  const saveGroup = () => {
    const name = groupName.trim()
    if (!name || picked.size === 0) return
    setSaving(true)
    const names = [...picked.keys()]
    const p = editingId
      ? saleAnalysisService.updateGroup(tenantId, editingId, name, names)
      : saleAnalysisService.createGroup(tenantId, name, names)
    p.then(() => { reloadGroups(); closeBuilder() })
      .catch((err) => setError(err instanceof Error ? err.message : 'Save failed'))
      .finally(() => setSaving(false))
  }

  const deleteGroup = (g: SaleGroupSummary) => {
    if (!globalThis.confirm(`Delete group "${g.group_name}"?`)) return
    saleAnalysisService.deleteGroup(tenantId, g.group_id).then(() => {
      setSelected((cur) => { const s = new Set(cur); s.delete(g.group_id); return s })
      reloadGroups()
    }).catch((err) => setError(err instanceof Error ? err.message : 'Delete failed'))
  }

  const toggleSelected = (id: string) => {
    setSelected((cur) => { const s = new Set(cur); if (s.has(id)) s.delete(id); else s.add(id); return s })
  }
  const toggleExpanded = (name: string) => {
    setExpanded((cur) => { const s = new Set(cur); if (s.has(name)) s.delete(name); else s.add(name); return s })
  }

  // --- export -------------------------------------------------------------
  const safeName = (s: string) => s.replace(/[^\w.-]+/g, '_').slice(0, 60)
  const exportExcel = () => {
    if (!result || result.groups.length === 0) return
    const exportCols: ExpiryColumn[] = [
      { key: 'Group', label: 'Group', align: 'left', format: null },
      ...result.columns.filter((c) => c.key !== 'SupplierName'),
    ]
    const rows: Record<string, unknown>[] = []
    result.groups.forEach((g) => {
      g.rows.forEach((r) => rows.push({ Group: g.group_name, ...r }))
      rows.push({ Group: g.group_name, ...g.summary, Name: 'Subtotal' })
    })
    const summary = result.grand_summary ? { Group: 'Total', ...result.grand_summary } : null
    void exportExpiryExcel({
      columns: exportCols,
      rows,
      summary,
      sheetName: 'sale-analysis',
      fileName: safeName(`sale-analysis-${result.window_label}`),
      title: `Sale Analysis — ${result.window_label} — cover ${result.target_days}d`,
    })
  }

  const storeName = tenantStores.find((s) => s.store_id === storeId)?.store_name ?? 'Store'
  const canRun = tenantId && storeId && selected.size > 0

  return (
    <div className="container-fluid px-0 rpt">
      <PageHeader title="Sale Analysis" breadcrumb={['Inventory', 'Sale Analysis']} />

      <FilterBar compact className="rpt-bar" ariaLabel="Sale analysis filters">
        <select className="form-select form-select-sm" aria-label="Tenant" value={tenantId} onChange={(e) => setTenantId(e.target.value)}>
          {tenants.length === 0 && <option value="">Loading…</option>}
          {tenants.map((t) => <option key={t.tenant_id} value={t.tenant_id}>{t.tenant_name}</option>)}
        </select>
        <select className="form-select form-select-sm" aria-label="Store" value={storeId} onChange={(e) => setStoreId(e.target.value)}>
          {tenantStores.length === 0 && <option value="">No stores</option>}
          {tenantStores.map((s) => <option key={s.store_id} value={s.store_id}>{s.store_name}</option>)}
        </select>
        <select className="form-select form-select-sm" aria-label="Window" value={window} onChange={(e) => setWindow(e.target.value as SaleWindow)}>
          {WINDOWS.map((w) => <option key={w.key} value={w.key}>{w.label}</option>)}
        </select>
        {window === 'range' && (
          <>
            <label className="rpt-field"><span>From</span>
              <input type="date" className="form-control form-control-sm" value={fromDate} onChange={(e) => setFromDate(e.target.value)} />
            </label>
            <label className="rpt-field"><span>To</span>
              <input type="date" className="form-control form-control-sm" value={toDate} onChange={(e) => setToDate(e.target.value)} />
            </label>
          </>
        )}
        <label className="rpt-field"><span>Cover target (days)</span>
          <input type="number" min={1} className="form-control form-control-sm" style={{ width: 90 }}
            value={targetDays} onChange={(e) => setTargetDays(Number(e.target.value))} />
        </label>
        <button className="btn btn-primary btn-sm" disabled={!canRun} onClick={runReport}>
          <i className="bi bi-play-fill" /> Run
        </button>
        <button className="btn btn-outline-secondary btn-sm" disabled={!result || result.groups.length === 0} onClick={exportExcel}>
          <i className="bi bi-file-earmark-excel" /> Export Excel
        </button>
      </FilterBar>

      <div className="sa-layout">
        {/* Left: group management */}
        <div className="sa-panel">
          <h3>Product Groups</h3>
          {groups.length === 0 ? (
            <p className="sa-empty-hint">No groups yet. Create one to analyse a product family.</p>
          ) : (
            <ul className="sa-groups">
              {groups.map((g) => (
                <li key={g.group_id} className="sa-group-row">
                  <label>
                    <input type="checkbox" checked={selected.has(g.group_id)} onChange={() => toggleSelected(g.group_id)} />
                    <span className="sa-group-name">{g.group_name}</span>
                    <span className="sa-group-count">{g.item_count}</span>
                  </label>
                  <div className="sa-group-actions">
                    <button title="Edit" onClick={() => openEditBuilder(g)}><i className="bi bi-pencil" /></button>
                    <button title="Delete" onClick={() => deleteGroup(g)}><i className="bi bi-trash" /></button>
                  </div>
                </li>
              ))}
            </ul>
          )}

          {!builderOpen ? (
            <button className="btn btn-outline-primary btn-sm w-100 mt-2" onClick={openNewBuilder}>
              <i className="bi bi-plus-lg" /> New Group
            </button>
          ) : (
            <div className="sa-builder">
              <input className="form-control form-control-sm" placeholder="Group name (e.g. Friends Adult Diaper)"
                value={groupName} onChange={(e) => setGroupName(e.target.value)} />
              <select className="form-select form-select-sm" aria-label="Supplier filter" value={supplierFilter}
                onChange={(e) => setSupplierFilter(e.target.value)}>
                <option value="">All suppliers</option>
                {supplierOptions.map((s) => <option key={s.supplier_code} value={s.supplier_code}>{s.supplier_name || s.supplier_code}</option>)}
              </select>
              <input className="form-control form-control-sm" placeholder="Search product name (e.g. FRIENDS)…"
                value={query} onChange={(e) => setQuery(e.target.value)} />
              {(supplierFilter || query.trim()) && (
                <div className="sa-builder-bulk">
                  <button type="button" className="btn btn-outline-primary btn-sm"
                    disabled={addingAll} onClick={addAllProducts}
                    title="Add every product matching this supplier/search to the group">
                    <i className="bi bi-plus-square-fill" /> {addingAll ? 'Adding…' : 'Add all products'}
                  </button>
                  {picked.size > 0 && (
                    <button type="button" className="btn btn-outline-secondary btn-sm" onClick={clearPicked}>
                      Clear ({picked.size})
                    </button>
                  )}
                </div>
              )}
              {searchResults.length > 0 && (
                <ul className="sa-results">
                  {searchResults.map((p) => {
                    const isPicked = picked.has(p.product_name)
                    return (
                      <li key={p.product_code} className={`sa-result-row${isPicked ? ' picked' : ''}`}
                        onClick={() => (isPicked ? removeProduct(p.product_name) : addProduct(p))}>
                        <div className="sa-result-main">
                          <div className="sa-result-name">{p.product_name}</div>
                          <div className="sa-result-sub">{p.product_code} · stock {num(p.current_stock)}{p.supplier_name ? ` · ${p.supplier_name}` : ''}</div>
                        </div>
                        <i className={`bi ${isPicked ? 'bi-check-square-fill' : 'bi-plus-square'}`} />
                      </li>
                    )
                  })}
                </ul>
              )}
              {picked.size > 0 && (
                <div className="sa-chips">
                  {[...picked.values()].map((p) => (
                    <span key={p.product_name} className="sa-chip">
                      {p.product_name}
                      <button title="Remove" onClick={() => removeProduct(p.product_name)}>×</button>
                    </span>
                  ))}
                </div>
              )}
              <div className="sa-builder-actions">
                <button className="btn btn-primary btn-sm" disabled={saving || !groupName.trim() || picked.size === 0} onClick={saveGroup}>
                  {saving ? 'Saving…' : editingId ? 'Update Group' : 'Save Group'}
                </button>
                <button className="btn btn-outline-secondary btn-sm" onClick={closeBuilder}>Cancel</button>
              </div>
            </div>
          )}
        </div>

        {/* Right: report */}
        <div>
          {error ? (
            <ErrorState description={error} onRetry={runReport} />
          ) : loading ? (
            <EmptyState icon="bi-hourglass-split" title="Loading…" description="Crunching stock vs sales." />
          ) : !result ? (
            <EmptyState icon="bi-graph-up-arrow" title="Select group(s) and Run"
              description="Tick one or more product groups on the left, choose a window, then Run." />
          ) : result.groups.every((g) => g.rows.length === 0) ? (
            <EmptyState icon="bi-inbox" title="No products" description="The selected group(s) have no matching products in this store." />
          ) : (
            <>
              {/* Summary table */}
              <div className="rpt-tablewrap">
                <table className="rpt-table">
                  <caption className="visually-hidden">Group summary</caption>
                  <thead>
                    <tr>{result.columns.filter((c) => c.key !== 'SupplierName').map((c) => (
                      <th key={c.key} className={`rpt-${c.align}`}>{c.label}</th>
                    ))}</tr>
                  </thead>
                  <tbody>
                    {result.groups.map((g) => (
                      <tr key={g.group_name}>
                        {result.columns.filter((c) => c.key !== 'SupplierName').map((c) => (
                          <td key={c.key} className={`rpt-${c.align}`}>{cell(g.summary[c.key], c)}</td>
                        ))}
                      </tr>
                    ))}
                    {result.grand_summary && (
                      <tr className="rpt-total">
                        {result.columns.filter((c) => c.key !== 'SupplierName').map((c) => (
                          <td key={c.key} className={`rpt-${c.align}`}>{cell(result.grand_summary![c.key], c)}</td>
                        ))}
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>

              {/* Detail per group */}
              <div className="text-muted small mt-2 mb-1">
                {result.window_label} · window {result.window_days} days · cover target {result.target_days} days · {storeName}
              </div>
              {result.groups.map((g) => (
                <div key={g.group_name}>
                  <div className="sa-group-title" onClick={() => toggleExpanded(g.group_name)}>
                    <i className={`bi ${expanded.has(g.group_name) ? 'bi-chevron-down' : 'bi-chevron-right'}`} />
                    {g.group_name} <span className="sa-group-count">({g.rows.length})</span>
                  </div>
                  {expanded.has(g.group_name) && (
                    <div className="rpt-tablewrap">
                      <table className="rpt-table">
                        <thead>
                          <tr>{result.columns.map((c) => <th key={c.key} className={`rpt-${c.align}`}>{c.label}</th>)}</tr>
                        </thead>
                        <tbody>
                          {g.rows.map((row, i) => (
                            <tr key={i}>
                              {result.columns.map((c) => <td key={c.key} className={`rpt-${c.align}`}>{cell(row[c.key], c)}</td>)}
                            </tr>
                          ))}
                          <tr className="rpt-total">
                            {result.columns.map((c) => <td key={c.key} className={`rpt-${c.align}`}>{cell(g.summary[c.key], c)}</td>)}
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              ))}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
