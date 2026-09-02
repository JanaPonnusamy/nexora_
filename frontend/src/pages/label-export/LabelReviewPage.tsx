import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { PageHeader } from '../../components/common/PageHeader'
import { storeService } from '../../services/storeService'
import { tenantService } from '../../services/tenantService'
import { labelExporterService } from '../../services/labelExporterService'
import type {
  IncludeLabel,
  LabelReviewRow,
  LabelSuggestionRow,
  ProductKind,
} from '../../types/labelExporter'
import type { TenantStore } from '../../types/store'
import type { Tenant } from '../../types/tenant'
import { canChangeLabelExportStore, isSuperAdmin } from './labelExportAccess'
import { useAuth } from '../../hooks/useAuth'
import { FilterBar } from '../../design-system/components/FilterBar'
import './label-export.css'

type Draft = { includeLabel: IncludeLabel | null; productKind: ProductKind | null; suggestedUnit: string }

function draftFromRow(row: LabelReviewRow): Draft {
  return {
    includeLabel: row.include_label,
    productKind: row.product_kind,
    suggestedUnit: row.suggested_unit_description || '',
  }
}

export default function LabelReviewPage() {
  const { user } = useAuth()
  const canChangeStore = canChangeLabelExportStore(user)
  const admin = isSuperAdmin(user)

  const [tenants, setTenants] = useState<Tenant[]>([])
  const [tenantId, setTenantId] = useState('')
  const [stores, setStores] = useState<TenantStore[]>([])
  const [storeId, setStoreId] = useState('')
  const [startsWith, setStartsWith] = useState('A')

  const [rows, setRows] = useState<LabelReviewRow[]>([])
  const [drafts, setDrafts] = useState<Record<string, Draft>>({})
  const [savingCode, setSavingCode] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [suggestions, setSuggestions] = useState<LabelSuggestionRow[]>([])
  const [suggestionDrafts, setSuggestionDrafts] = useState<Record<string, string>>({})
  const [decidingKey, setDecidingKey] = useState('')
  const [suggestionsLoading, setSuggestionsLoading] = useState(false)

  useEffect(() => {
    tenantService
      .list()
      .then((rows) => {
        const active = rows.filter((row) => row.is_active)
        setTenants(active)
        if (active.length) setTenantId((current) => current || active[0].tenant_id)
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load tenants'))
  }, [])

  useEffect(() => {
    if (!tenantId) return
    setStoreId('')
    storeService
      .getByTenant(tenantId)
      .then((rows) => {
        setStores(rows)
        const ownStore = rows.find((row) => row.store_id === user?.storeId)
        const defaultStore = (!canChangeStore && ownStore) || ownStore || rows[0]
        if (defaultStore) setStoreId((current) => current || defaultStore.store_id)
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load stores'))
  }, [tenantId, canChangeStore, user?.storeId])

  useEffect(() => {
    setRows([])
    setDrafts({})
  }, [tenantId, storeId])

  async function runSearch() {
    if (!tenantId || !storeId) return
    setLoading(true)
    setError(null)
    try {
      const result = await labelExporterService.listProductsForReview(tenantId, storeId, startsWith.trim())
      const nextRows = Array.isArray(result?.rows) ? result.rows : []
      setRows(nextRows)
      const nextDrafts: Record<string, Draft> = {}
      nextRows.forEach((row) => {
        if (row.product_code) nextDrafts[row.product_code] = draftFromRow(row)
      })
      setDrafts(nextDrafts)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load products for review')
    } finally {
      setLoading(false)
    }
  }

  const emptyDraft: Draft = { includeLabel: null, productKind: null, suggestedUnit: '' }

  function updateDraft(code: string, patch: Partial<Draft>) {
    setDrafts((current) => ({ ...current, [code]: { ...(current[code] || emptyDraft), ...patch } }))
  }

  async function saveRow(row: LabelReviewRow) {
    const draft = drafts[row.product_code]
    if (!draft) return
    setSavingCode(row.product_code)
    setError(null)
    try {
      const suggestionChanged = draft.suggestedUnit.trim() !== (row.suggested_unit_description || '').trim()
      await labelExporterService.updateReview(tenantId, storeId, row.product_code, {
        include_label: draft.includeLabel,
        product_kind: draft.productKind,
        suggested_unit_description: suggestionChanged ? draft.suggestedUnit.trim() : undefined,
      })
      setRows((current) =>
        current.map((r) =>
          r.product_code === row.product_code
            ? {
                ...r,
                include_label: draft.includeLabel,
                product_kind: draft.productKind,
                suggested_unit_description: suggestionChanged ? draft.suggestedUnit.trim() || null : r.suggested_unit_description,
                suggestion_status: suggestionChanged ? 'pending' : r.suggestion_status,
              }
            : r,
        ),
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save review')
    } finally {
      setSavingCode('')
    }
  }

  async function loadSuggestions() {
    setSuggestionsLoading(true)
    setError(null)
    try {
      const result = await labelExporterService.listPendingSuggestions(tenantId, storeId)
      const nextRows = Array.isArray(result?.rows) ? result.rows : []
      setSuggestions(nextRows)
      const nextDrafts: Record<string, string> = {}
      nextRows.forEach((row) => {
        nextDrafts[row.product_code] = row.suggested_unit_description || ''
      })
      setSuggestionDrafts(nextDrafts)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load pending suggestions')
    } finally {
      setSuggestionsLoading(false)
    }
  }

  useEffect(() => {
    if (admin) void loadSuggestions()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [admin, tenantId, storeId])

  async function decide(row: LabelSuggestionRow, approved: boolean) {
    const key = `${row.tenant_id}/${row.store_id}/${row.product_code}`
    setDecidingKey(key)
    setError(null)
    try {
      await labelExporterService.decideSuggestion(
        row.tenant_id,
        row.store_id,
        row.product_code,
        approved,
        approved ? suggestionDrafts[row.product_code] : undefined,
      )
      setSuggestions((current) => current.filter((s) => s !== row))
      setRows((current) =>
        current.map((r) =>
          r.product_code === row.product_code
            ? {
                ...r,
                suggestion_status: approved ? 'approved' : 'rejected',
                final_unit_description: approved ? suggestionDrafts[row.product_code] : r.final_unit_description,
              }
            : r,
        ),
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to record decision')
    } finally {
      setDecidingKey('')
    }
  }

  return (
    <div className="d-flex flex-column gap-3">
      <PageHeader title="Label Review" breadcrumb={['Operations', 'Inventory', 'Label Review']} />

      <FilterBar compact className="label-export-toolbar label-export-toolbar--compact" ariaLabel="Label review filters">
        <label className="label-export-field">
          <span className="label-export-field__label">Tenant</span>
          <select className="form-select form-select-sm" value={tenantId} onChange={(e) => setTenantId(e.target.value)}>
            {tenants.length === 0 && <option value="">Loading...</option>}
            {tenants.map((t) => (
              <option key={t.tenant_id} value={t.tenant_id}>{t.tenant_name}</option>
            ))}
          </select>
        </label>

        <label className="label-export-field">
          <span className="label-export-field__label">Store</span>
          <select
            className="form-select form-select-sm"
            value={storeId}
            disabled={!canChangeStore}
            onChange={(e) => setStoreId(e.target.value)}
          >
            {stores.length === 0 && <option value="">Loading...</option>}
            {(canChangeStore ? stores : stores.filter((s) => s.store_id === storeId)).map((s) => (
              <option key={s.store_id} value={s.store_id}>{s.store_code} - {s.store_name}</option>
            ))}
          </select>
        </label>

        <label className="label-export-field label-export-field--letter">
          <span className="label-export-field__label">Letter</span>
          <input
            className="form-control form-control-sm"
            value={startsWith}
            onChange={(e) => setStartsWith(e.target.value.replace(/[^a-z]/gi, '').toUpperCase().slice(0, 1))}
            placeholder="A"
            maxLength={1}
          />
        </label>

        <div className="label-export-actions-row">
          <button className="btn btn-primary btn-sm label-export-search-btn" disabled={!tenantId || !storeId || loading} onClick={() => void runSearch()}>
            {loading ? 'Loading...' : 'Load letter'}
          </button>
          <Link className="btn btn-outline-secondary btn-sm label-export-search-btn" to="/label-exporter">
            Label Exporter
          </Link>
        </div>
      </FilterBar>

      {error && <div className="alert alert-danger py-2 small mb-0">{error}</div>}

      <section className="card shadow-sm">
        <div className="card-header d-flex justify-content-between align-items-center">
          <strong>Products {startsWith ? `- ${startsWith}` : ''}</strong>
          <span className="small text-muted">{rows.length} product(s)</span>
        </div>
        <div className="card-body p-0">
          <div className="table-responsive label-export-scroll">
            <table className="table table-sm table-hover align-middle mb-0 label-export-table">
              <thead className="table-light">
                <tr>
                  <th>Code</th>
                  <th>Product</th>
                  <th>Current Unit</th>
                  <th>Include</th>
                  <th>Type</th>
                  <th>Suggested Unit</th>
                  <th>Status</th>
                  <th className="text-end">Save</th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 ? (
                  <tr><td colSpan={8} className="text-center text-muted py-4">Pick a letter and load products to review</td></tr>
                ) : (
                  rows.map((row) => {
                    const draft = drafts[row.product_code] || draftFromRow(row)
                    return (
                      <tr key={row.product_code}>
                        <td>{row.product_code}</td>
                        <td>{row.product_name}</td>
                        <td>{row.unit_description || <span className="text-danger">NULL</span>}</td>
                        <td>
                          <div className="btn-group btn-group-sm" role="group">
                            <button
                              type="button"
                              className={`btn ${draft.includeLabel === 'Y' ? 'btn-success' : 'btn-outline-success'}`}
                              onClick={() => updateDraft(row.product_code, { includeLabel: 'Y' })}
                            >
                              Y
                            </button>
                            <button
                              type="button"
                              className={`btn ${draft.includeLabel === 'N' ? 'btn-danger' : 'btn-outline-danger'}`}
                              onClick={() => updateDraft(row.product_code, { includeLabel: 'N' })}
                            >
                              N
                            </button>
                          </div>
                        </td>
                        <td>
                          <select
                            className="form-select form-select-sm"
                            value={draft.productKind || ''}
                            onChange={(e) => updateDraft(row.product_code, { productKind: (e.target.value || null) as ProductKind | null })}
                          >
                            <option value="">-</option>
                            <option value="counter">Counter</option>
                            <option value="consumer">Consumer</option>
                          </select>
                        </td>
                        <td>
                          <input
                            className="form-control form-control-sm"
                            value={draft.suggestedUnit}
                            placeholder="Suggest correction"
                            onChange={(e) => updateDraft(row.product_code, { suggestedUnit: e.target.value })}
                          />
                        </td>
                        <td>
                          {row.suggestion_status === 'pending' && <span className="badge text-bg-warning">Pending</span>}
                          {row.suggestion_status === 'approved' && <span className="badge text-bg-success">Approved: {row.final_unit_description}</span>}
                          {row.suggestion_status === 'rejected' && <span className="badge text-bg-secondary">Rejected</span>}
                          {row.suggestion_status === 'none' && <span className="text-muted small">-</span>}
                        </td>
                        <td className="text-end">
                          <button
                            className="btn btn-sm btn-outline-primary"
                            disabled={savingCode === row.product_code}
                            onClick={() => void saveRow(row)}
                          >
                            {savingCode === row.product_code ? '...' : 'Save'}
                          </button>
                        </td>
                      </tr>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {admin && (
        <section className="card shadow-sm">
          <div className="card-header d-flex justify-content-between align-items-center">
            <strong>Pending Unit-Description Suggestions</strong>
            <button className="btn btn-sm btn-outline-secondary" disabled={suggestionsLoading} onClick={() => void loadSuggestions()}>
              {suggestionsLoading ? 'Loading...' : 'Refresh'}
            </button>
          </div>
          <div className="card-body p-0">
            <div className="table-responsive label-export-scroll">
              <table className="table table-sm table-hover align-middle mb-0 label-export-table">
                <thead className="table-light">
                  <tr>
                    <th>Product</th>
                    <th>Current Unit</th>
                    <th>Suggested Unit</th>
                    <th>Final Unit (editable)</th>
                    <th className="text-end">Decision</th>
                  </tr>
                </thead>
                <tbody>
                  {suggestions.length === 0 ? (
                    <tr><td colSpan={5} className="text-center text-muted py-4">No pending suggestions</td></tr>
                  ) : (
                    suggestions.map((row) => {
                      const key = `${row.tenant_id}/${row.store_id}/${row.product_code}`
                      return (
                        <tr key={key}>
                          <td>
                            <div className="fw-semibold">{row.product_name}</div>
                            <div className="small text-muted">{row.product_code}</div>
                          </td>
                          <td>{row.current_unit_description || <span className="text-danger">NULL</span>}</td>
                          <td>{row.suggested_unit_description}</td>
                          <td>
                            <input
                              className="form-control form-control-sm"
                              value={suggestionDrafts[row.product_code] ?? ''}
                              onChange={(e) =>
                                setSuggestionDrafts((current) => ({ ...current, [row.product_code]: e.target.value }))
                              }
                            />
                          </td>
                          <td className="text-end">
                            <div className="btn-group btn-group-sm">
                              <button
                                className="btn btn-success"
                                disabled={decidingKey === key || !(suggestionDrafts[row.product_code] || '').trim()}
                                onClick={() => void decide(row, true)}
                              >
                                Approve
                              </button>
                              <button
                                className="btn btn-outline-danger"
                                disabled={decidingKey === key}
                                onClick={() => void decide(row, false)}
                              >
                                Reject
                              </button>
                            </div>
                          </td>
                        </tr>
                      )
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      )}
    </div>
  )
}
