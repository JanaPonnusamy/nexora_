import { useEffect, useMemo, useState } from 'react'
import { PageHeader } from '../../components/common/PageHeader'
import { EmptyState } from '../../components/common/EmptyState'
import { ErrorState } from '../../components/common/ErrorState'
import { DataTable, type DataTableColumn } from '../../components/common/DataTable/DataTable'
import { FilterBar, FilterSearch, FilterSelect } from '../../design-system/components/FilterBar'
import { api, ApiError } from '../../services/apiClient'
import { tenantService } from '../../services/tenantService'
import { storeService } from '../../services/storeService'
import { useActingUser } from '../../hooks/useActingUser'
import type { Tenant } from '../../types/tenant'
import type { TenantStore } from '../../types/store'

type CatalogRule = {
  rule_id: string
  name: string
  category: string
  group: string
  description: string
  source_evidence: string
  current_behavior: string
  target_behavior: string
  status: string
  value_type: string
  default_value: string | number | boolean | null
  validation: string
  override_policy: string
}

type EffectiveRule = {
  rule_id: string
  value: string | number | boolean | null
  source: 'default' | 'override'
  row_version: number
  default_row_version: number
  status: string
  override_policy: string
  inherited_value: string | number | boolean | null
}

type HistoryRow = {
  audit_id: string
  change_kind: string
  previous_value: string | number | boolean | null
  new_value: string | number | boolean | null
  editor_id: string
  reason: string
  changed_at: string
  row_version: number
}

type Row = CatalogRule & EffectiveRule

const GROUPS = [
  { value: '', label: 'All groups' },
  { value: 'common_confirmed', label: 'Confirmed' },
  { value: 'legacy_nexora_conflict', label: 'Legacy vs Nexora' },
  { value: 'store_configurable', label: 'Store configurable' },
  { value: 'locked_safety', label: 'Locked' },
  { value: 'unverified', label: 'Unverified' },
  { value: 'approval_required', label: 'Needs approval' },
]

function show(value: string | number | boolean | null | undefined) {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  return String(value)
}

function parseInput(valueType: string, raw: string): string | number | boolean {
  if (valueType === 'int') return Number(raw)
  if (valueType === 'bool') return raw === 'true'
  return raw
}

export default function ProcurementRulesPage() {
  const editorId = useActingUser()
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [stores, setStores] = useState<TenantStore[]>([])
  const [tenantId, setTenantId] = useState('')
  const [storeId, setStoreId] = useState('')
  const [catalog, setCatalog] = useState<CatalogRule[]>([])
  const [effective, setEffective] = useState<EffectiveRule[]>([])
  const [query, setQuery] = useState('')
  const [group, setGroup] = useState('')
  const [status, setStatus] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [history, setHistory] = useState<HistoryRow[]>([])
  const [draft, setDraft] = useState('')
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const loadCatalog = async () => {
    const body = await api.get<{ rules: CatalogRule[] }>('/api/procurement/rules/catalog')
    setCatalog(body.rules)
  }

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const [tenantRows] = await Promise.all([tenantService.list(), loadCatalog()])
        if (!cancelled) setTenants(tenantRows)
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiError ? err.message : 'The rules catalog could not be loaded.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!tenantId) {
      setStores([])
      setStoreId('')
      return
    }
    let cancelled = false
    storeService.getActiveByTenant(tenantId).then((rows) => {
      if (!cancelled) {
        setStores(rows)
        setStoreId(rows[0]?.store_id ?? '')
      }
    }).catch((err) => {
      if (!cancelled) setError(err instanceof ApiError ? err.message : 'Stores could not be loaded.')
    })
    return () => {
      cancelled = true
    }
  }, [tenantId])

  const loadEffective = async (nextTenant: string, nextStore: string) => {
    const body = await api.get<{ rules: EffectiveRule[] }>(
      `/api/procurement/rules/effective?tenant_id=${encodeURIComponent(nextTenant)}&store_id=${encodeURIComponent(nextStore)}`,
    )
    setEffective(body.rules)
  }

  useEffect(() => {
    if (!tenantId || !storeId) {
      setEffective([])
      return
    }
    let cancelled = false
    loadEffective(tenantId, storeId).catch((err) => {
      if (!cancelled) setError(err instanceof ApiError ? err.message : 'Effective rules could not be loaded.')
    })
    return () => {
      cancelled = true
    }
  }, [tenantId, storeId])

  const rows = useMemo<Row[]>(() => {
    const byId = new Map(effective.map((row) => [row.rule_id, row]))
    return catalog
      .map((rule) => {
        const live = byId.get(rule.rule_id)
        return {
          ...rule,
          value: live?.value ?? rule.default_value,
          source: live?.source ?? 'default',
          row_version: live?.row_version ?? 1,
          default_row_version: live?.default_row_version ?? 1,
          inherited_value: live?.inherited_value ?? rule.default_value,
          override_policy: live?.override_policy ?? rule.override_policy,
          status: live?.status ?? rule.status,
        }
      })
      .filter((row) => {
        const haystack = `${row.rule_id} ${row.name} ${row.description}`.toLowerCase()
        if (query && !haystack.includes(query.toLowerCase())) return false
        if (group && row.group !== group) return false
        if (status && row.status !== status) return false
        return true
      })
  }, [catalog, effective, query, group, status])

  const selected = rows.find((row) => row.rule_id === selectedId) ?? null

  const openRow = async (row: Row) => {
    setSelectedId(row.rule_id)
    setDraft(row.value === null || row.value === undefined ? '' : String(row.value))
    setReason('')
    setNotice(null)
    if (!tenantId) {
      setHistory([])
      return
    }
    const body = await api.get<{ changes: HistoryRow[] }>(
      `/api/procurement/rules/history?tenant_id=${encodeURIComponent(tenantId)}&store_id=${encodeURIComponent(storeId)}&rule_id=${encodeURIComponent(row.rule_id)}`,
    )
    setHistory(body.changes)
  }

  const save = async (kind: 'override' | 'default') => {
    if (!selected) return
    setError(null)
    setNotice(null)
    const value = parseInput(selected.value_type, draft)
    const payload = {
      value,
      editor_id: editorId,
      reason,
      expected_version: kind === 'default' ? selected.default_row_version : selected.source === 'override' ? selected.row_version : 0,
    }
    try {
      if (kind === 'default') {
        await api.put(`/api/procurement/rules/defaults/${selected.rule_id}`, payload)
      } else {
        await api.put(
          `/api/procurement/rules/overrides/${selected.rule_id}?tenant_id=${encodeURIComponent(tenantId)}&store_id=${encodeURIComponent(storeId)}`,
          payload,
        )
      }
      setNotice('Saved for future calculations. Existing orders and the live decision engine were not recalculated.')
      await loadEffective(tenantId, storeId)
      await openRow({ ...selected, rule_id: selected.rule_id })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Save failed.')
    }
  }

  const reset = async () => {
    if (!selected || selected.source !== 'override') return
    if (!window.confirm(`Reset ${selected.rule_id} to the inherited default?`)) return
    setError(null)
    try {
      await api.post(
        `/api/procurement/rules/overrides/${selected.rule_id}/reset?tenant_id=${encodeURIComponent(tenantId)}&store_id=${encodeURIComponent(storeId)}`,
        { value: null, editor_id: editorId, reason: reason || 'Reset to inherited default', expected_version: selected.row_version },
      )
      setNotice('Store override removed. Future calculations inherit the default.')
      await loadEffective(tenantId, storeId)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Reset failed.')
    }
  }

  const columns: DataTableColumn<Row>[] = [
    { key: 'rule_id', header: 'ID', accessor: (row) => row.rule_id, sortable: true },
    { key: 'name', header: 'Rule', accessor: (row) => row.name, sortable: true },
    { key: 'status', header: 'Status', accessor: (row) => row.status, sortable: true },
    { key: 'source', header: 'Source', accessor: (row) => (row.source === 'override' ? 'Store override' : 'Inherited'), sortable: true },
    { key: 'value', header: 'Effective', accessor: (row) => show(row.value) },
  ]

  const statuses = Array.from(new Set(catalog.map((rule) => rule.status))).sort()

  return (
    <div className="page-content">
      <PageHeader
        title="Procurement rules"
        breadcrumb={['Procurement', 'Rules']}
        description="Defaults and store overrides for future order calculations. Profile T stays off the live decision engine."
      />
      <div className="alert alert-warning" role="status">
        Changes here do not recalculate a confirmed or exported order. Migration 0026 is not applied, so saved overrides live in this API process until that migration is approved.
      </div>
      {error && <ErrorState title="Rules registry" description={error} onRetry={() => window.location.reload()} />}
      {notice && <div className="alert alert-info">{notice}</div>}
      <FilterBar>
        <FilterSelect
          ariaLabel="Tenant"
          value={tenantId}
          onChange={setTenantId}
          options={[{ value: '', label: 'Select tenant' }, ...tenants.map((tenant) => ({ value: tenant.tenant_id, label: tenant.tenant_name }))]}
        />
        <FilterSelect
          ariaLabel="Store"
          value={storeId}
          onChange={setStoreId}
          options={[{ value: '', label: 'Select store' }, ...stores.map((store) => ({ value: store.store_id, label: store.store_name }))]}
        />
        <FilterSelect ariaLabel="Group" value={group} onChange={setGroup} options={GROUPS} />
        <FilterSelect
          ariaLabel="Status"
          value={status}
          onChange={setStatus}
          options={[{ value: '', label: 'All statuses' }, ...statuses.map((item) => ({ value: item, label: item }))]}
        />
        <FilterSearch value={query} onChange={setQuery} placeholder="Search rules" ariaLabel="Search rules" />
      </FilterBar>
      {loading ? null : rows.length === 0 ? (
        <EmptyState icon="bi-sliders" title="No rules match" description="Change the group, status, or search." />
      ) : (
        <DataTable columns={columns} data={rows} getRowId={(row) => row.rule_id} onRowClick={(row) => { void openRow(row) }} />
      )}
      {selected && (
        <section className="mt-3" aria-label="Rule detail">
          <h2 className="h6">{selected.rule_id} — {selected.name}</h2>
          <p>{selected.description}</p>
          <p><strong>Source evidence.</strong> {selected.source_evidence}</p>
          <p><strong>Current behavior.</strong> {selected.current_behavior}</p>
          <p><strong>Target behavior.</strong> {selected.target_behavior}</p>
          <p><strong>Validation.</strong> {selected.validation}</p>
          <p>
            Inherited: {show(selected.inherited_value)}. Effective: {show(selected.value)} ({selected.source}).
          </p>
          {selected.override_policy !== 'STORE_OVERRIDE' ? (
            <p className="text-danger">Locked. A store cannot override this rule. {selected.status === 'DECISION_REQUIRED' || selected.status === 'UNVERIFIED' ? 'The value is unresolved, so it is not editable.' : ''}</p>
          ) : (
            <form
              onSubmit={(event) => {
                event.preventDefault()
              }}
            >
              <label className="form-label" htmlFor="rule-draft">Value</label>
              <input id="rule-draft" className="form-control form-control-sm mb-2" value={draft} onChange={(event) => setDraft(event.target.value)} />
              <label className="form-label" htmlFor="rule-reason">Reason</label>
              <input id="rule-reason" className="form-control form-control-sm mb-2" value={reason} onChange={(event) => setReason(event.target.value)} />
              <div className="d-flex gap-2">
                <button type="button" className="btn btn-primary btn-sm" disabled={!storeId || !reason.trim()} onClick={() => { void save('override') }}>
                  Save store override
                </button>
                <button type="button" className="btn btn-outline-secondary btn-sm" disabled={!reason.trim()} onClick={() => { void save('default') }}>
                  Save default
                </button>
                <button type="button" className="btn btn-outline-danger btn-sm" disabled={selected.source !== 'override' || !reason.trim()} onClick={() => { void reset() }}>
                  Reset to inherited
                </button>
              </div>
            </form>
          )}
          <h3 className="h6 mt-3">Change history</h3>
          {history.length === 0 ? <p>No changes for this store and rule.</p> : (
            <ul>
              {history.map((row) => (
                <li key={row.audit_id}>
                  {row.changed_at} · {row.change_kind} · version {row.row_version} · {row.editor_id} · {show(row.previous_value)} → {show(row.new_value)} · {row.reason}
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  )
}
