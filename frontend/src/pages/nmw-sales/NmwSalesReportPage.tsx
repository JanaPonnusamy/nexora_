import { Fragment, useCallback, useEffect, useMemo, useState } from 'react'
import { PageHeader } from '../../components/common/PageHeader'
import { tenantService } from '../../services/tenantService'
import { storeService } from '../../services/storeService'
import { nmwSalesReportService } from '../../services/nmwSalesReportService'
import type { Tenant } from '../../types/tenant'
import type { TenantStore } from '../../types/store'
import type { NmwSalesBill, NmwSalesBillItem } from '../../types/nmwSalesReport'

type StatusFilter = 'all' | 'pending' | 'approved'

function billKey(bill: NmwSalesBill): string {
  return `${bill.bill_date ?? ''}|${bill.bill_no ?? ''}`
}

function money(value: number | null | undefined): string {
  const n = Number(value)
  return Number.isFinite(n) ? n.toFixed(2) : '-'
}

export default function NmwSalesReportPage() {
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [tenantId, setTenantId] = useState('')
  const [stores, setStores] = useState<TenantStore[]>([])
  const [storeId, setStoreId] = useState('')
  const [status, setStatus] = useState<StatusFilter>('all')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [bills, setBills] = useState<NmwSalesBill[]>([])
  const [canApprove, setCanApprove] = useState(false)
  const [scope, setScope] = useState<'store' | 'all'>('store')

  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [expanded, setExpanded] = useState<string | null>(null)
  const [items, setItems] = useState<Record<string, NmwSalesBillItem[]>>({})
  const [showCustCodes, setShowCustCodes] = useState(false)

  useEffect(() => {
    tenantService
      .list()
      .then((list) => {
        const active = list.filter((t) => t.is_active)
        setTenants(active)
        if (active.length) setTenantId((cur) => cur || active[0].tenant_id)
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load tenants'))
  }, [])

  useEffect(() => {
    if (!tenantId) return
    storeService
      .getByTenant(tenantId)
      .then((list) => setStores(list))
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load stores'))
  }, [tenantId])

  const load = useCallback(async () => {
    if (!tenantId) return
    setLoading(true)
    setError(null)
    setNotice(null)
    setSelected(new Set())
    setExpanded(null)
    try {
      const result = await nmwSalesReportService.listBills(tenantId, {
        storeId: storeId || undefined,
        status,
        dateFrom: dateFrom || undefined,
        dateTo: dateTo || undefined,
      })
      setBills(result.bills)
      setCanApprove(result.can_approve)
      setScope(result.scope)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load bills')
      setBills([])
    } finally {
      setLoading(false)
    }
  }, [tenantId, storeId, status, dateFrom, dateTo])

  async function toggleExpand(bill: NmwSalesBill) {
    const key = billKey(bill)
    if (expanded === key) {
      setExpanded(null)
      return
    }
    setExpanded(key)
    if (!items[key] && bill.bill_no && bill.bill_date) {
      try {
        const result = await nmwSalesReportService.billItems(tenantId, bill.bill_no, bill.bill_date)
        setItems((prev) => ({ ...prev, [key]: result.items }))
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load bill items')
      }
    }
  }

  function toggleSelect(bill: NmwSalesBill) {
    const key = billKey(bill)
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const pendingBills = useMemo(() => bills.filter((b) => b.status !== 'approved'), [bills])
  const allPendingSelected = pendingBills.length > 0 && pendingBills.every((b) => selected.has(billKey(b)))

  function toggleSelectAll() {
    if (allPendingSelected) {
      setSelected(new Set())
    } else {
      setSelected(new Set(pendingBills.map(billKey)))
    }
  }

  async function approve(target: NmwSalesBill[]) {
    const keys = target.filter((b) => b.bill_no && b.bill_date)
    if (!keys.length) return
    setLoading(true)
    setError(null)
    try {
      const result = await nmwSalesReportService.approve(
        tenantId,
        keys.map((b) => ({ bill_date: b.bill_date as string, bill_no: b.bill_no as string })),
      )
      setNotice(`Approved ${result.approved} bill(s).`)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Approval failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="d-flex flex-column gap-3">
      <PageHeader
        title="NMW Sales Report (Bill-wise)"
        breadcrumb={['Operations', 'Inventory', 'NMW Sales Report']}
        description="Warehouse (NMW) despatch bills routed to each store. Bills appear once despatched; a super admin approves the despatch before store devices display them."
      />

      <div className="ds-toolbar d-flex flex-wrap gap-3 align-items-end">
        <label className="d-flex flex-column gap-1">
          <span className="small text-muted">Tenant</span>
          <select className="form-select" value={tenantId} onChange={(e) => setTenantId(e.target.value)}>
            {tenants.length === 0 && <option value="">Loading...</option>}
            {tenants.map((t) => (
              <option key={t.tenant_id} value={t.tenant_id}>
                {t.tenant_name}
              </option>
            ))}
          </select>
        </label>

        <label className="d-flex flex-column gap-1">
          <span className="small text-muted">Destination store</span>
          <select className="form-select" value={storeId} onChange={(e) => setStoreId(e.target.value)}>
            <option value="">All stores</option>
            {stores.map((s) => (
              <option key={s.store_id} value={s.store_id}>
                {s.store_code} — {s.store_name}
              </option>
            ))}
          </select>
        </label>

        <label className="d-flex flex-column gap-1">
          <span className="small text-muted">Status</span>
          <select className="form-select" value={status} onChange={(e) => setStatus(e.target.value as StatusFilter)}>
            <option value="all">All</option>
            <option value="pending">Pending</option>
            <option value="approved">Approved</option>
          </select>
        </label>

        <label className="d-flex flex-column gap-1">
          <span className="small text-muted">From</span>
          <input type="date" className="form-control" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
        </label>

        <label className="d-flex flex-column gap-1">
          <span className="small text-muted">To</span>
          <input type="date" className="form-control" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
        </label>

        <button className="btn btn-primary" disabled={!tenantId || loading} onClick={() => void load()}>
          <i className="bi bi-eye me-1" />
          {loading ? 'Loading…' : 'Load'}
        </button>

        {canApprove && (
          <>
            <button
              className="btn btn-success"
              disabled={loading || selected.size === 0}
              onClick={() => void approve(pendingBills.filter((b) => selected.has(billKey(b))))}
            >
              <i className="bi bi-check2-all me-1" />
              Approve selected ({selected.size})
            </button>
            <button className="btn btn-outline-secondary" onClick={() => setShowCustCodes((v) => !v)}>
              <i className="bi bi-upc-scan me-1" />
              Store customer codes
            </button>
          </>
        )}
      </div>

      {scope === 'store' && (
        <div className="alert alert-secondary py-2 small mb-0">
          You are viewing only your own store's approved bills.
        </div>
      )}
      {notice && <div className="alert alert-success py-2 small mb-0">{notice}</div>}
      {error && <div className="alert alert-danger py-2 small mb-0">{error}</div>}

      {showCustCodes && canApprove && <StoreCustCodePanel tenantId={tenantId} onDone={() => void load()} />}

      {bills.length > 0 ? (
        <div className="table-responsive">
          <table className="table table-sm table-bordered align-middle mb-0">
            <thead>
              <tr className="table-light">
                {canApprove && (
                  <th style={{ width: '2rem' }}>
                    <input
                      type="checkbox"
                      className="form-check-input"
                      checked={allPendingSelected}
                      onChange={toggleSelectAll}
                      disabled={pendingBills.length === 0}
                      aria-label="Select all pending bills"
                    />
                  </th>
                )}
                <th style={{ whiteSpace: 'nowrap' }}>Bill No</th>
                <th style={{ whiteSpace: 'nowrap' }}>Type</th>
                <th style={{ whiteSpace: 'nowrap' }}>Bill Date</th>
                <th style={{ whiteSpace: 'nowrap' }}>Despatched</th>
                <th>Destination Store</th>
                <th style={{ whiteSpace: 'nowrap' }}>Cust Code</th>
                <th className="text-end" style={{ whiteSpace: 'nowrap' }}>Amount</th>
                <th style={{ whiteSpace: 'nowrap' }}>Status</th>
                <th style={{ whiteSpace: 'nowrap' }} />
              </tr>
            </thead>
            <tbody>
              {bills.map((bill) => {
                const key = billKey(bill)
                const isApproved = bill.status === 'approved'
                return (
                  <Fragment key={key}>
                    <tr>
                      {canApprove && (
                        <td>
                          {!isApproved && (
                            <input
                              type="checkbox"
                              className="form-check-input"
                              checked={selected.has(key)}
                              onChange={() => toggleSelect(bill)}
                              aria-label={`Select bill ${bill.bill_no}`}
                            />
                          )}
                        </td>
                      )}
                      <td style={{ whiteSpace: 'nowrap' }}>{bill.bill_no}</td>
                      <td style={{ whiteSpace: 'nowrap' }}>
                        <span className={`badge ${bill.is_transfer ? 'text-bg-info' : 'text-bg-secondary'}`}>
                          {bill.bill_type}
                        </span>
                      </td>
                      <td style={{ whiteSpace: 'nowrap' }}>{bill.bill_date}</td>
                      <td style={{ whiteSpace: 'nowrap' }}>{bill.issued_date?.slice(0, 19).replace('T', ' ')}</td>
                      <td>
                        {bill.dest_store_code} — {bill.dest_store_name}
                      </td>
                      <td style={{ whiteSpace: 'nowrap' }}>{bill.customer_code}</td>
                      <td className="text-end" style={{ whiteSpace: 'nowrap' }}>{money(bill.bill_amount)}</td>
                      <td style={{ whiteSpace: 'nowrap' }}>
                        {isApproved ? (
                          <span className="badge text-bg-success">Approved</span>
                        ) : (
                          <span className="badge text-bg-warning">Pending</span>
                        )}
                      </td>
                      <td className="text-nowrap">
                        <button className="btn btn-sm btn-outline-secondary me-1" onClick={() => void toggleExpand(bill)}>
                          {expanded === key ? 'Hide' : 'Items'}
                        </button>
                        {canApprove && !isApproved && (
                          <button className="btn btn-sm btn-success" onClick={() => void approve([bill])}>
                            Approve
                          </button>
                        )}
                      </td>
                    </tr>
                    {expanded === key && (
                      <tr>
                        <td colSpan={canApprove ? 10 : 9} className="p-0">
                          <BillItemsTable rows={items[key]} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
      ) : (
        !loading && <div className="text-muted small">No bills to show. Adjust filters and press Load.</div>
      )}
    </div>
  )
}

function BillItemsTable({ rows }: { rows: NmwSalesBillItem[] | undefined }) {
  if (!rows) return <div className="p-2 small text-muted">Loading items…</div>
  if (rows.length === 0) return <div className="p-2 small text-muted">No line items.</div>
  return (
    <table className="table table-sm mb-0">
      <thead>
        <tr className="table-light">
          <th>Product</th>
          <th style={{ whiteSpace: 'nowrap' }}>Batch</th>
          <th style={{ whiteSpace: 'nowrap' }}>Expiry</th>
          <th className="text-end">Qty</th>
          <th className="text-end">Free</th>
          <th className="text-end">MRP</th>
          <th className="text-end">Rate</th>
          <th className="text-end">Dis%</th>
          <th className="text-end">Amount</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={`${r.product_code}-${r.batch_no}-${i}`}>
            <td>{r.product_name}</td>
            <td style={{ whiteSpace: 'nowrap' }}>{r.batch_no}</td>
            <td style={{ whiteSpace: 'nowrap' }}>{r.expiry_date}</td>
            <td className="text-end">{r.qty}</td>
            <td className="text-end">{r.free_qty}</td>
            <td className="text-end">{money(r.mrp)}</td>
            <td className="text-end">{money(r.rate)}</td>
            <td className="text-end">{r.discount_percentage}</td>
            <td className="text-end">{money(r.amount)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function StoreCustCodePanel({ tenantId, onDone }: { tenantId: string; onDone: () => void }) {
  const [rows, setRows] = useState<{ store_id: string; store_code: string | null; store_name: string | null; ho_cust_code: string | null; ho_transfer_code: string | null }[]>([])
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [transferDraft, setTransferDraft] = useState<Record<string, string>>({})
  const [msg, setMsg] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(async () => {
    if (!tenantId) return
    try {
      const result = await nmwSalesReportService.listStoreCustCodes(tenantId)
      setRows(result.stores)
      setDraft(Object.fromEntries(result.stores.map((s) => [s.store_id, s.ho_cust_code ?? ''])))
      setTransferDraft(Object.fromEntries(result.stores.map((s) => [s.store_id, s.ho_transfer_code ?? ''])))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load store codes')
    }
  }, [tenantId])

  useEffect(() => {
    void reload()
  }, [reload])

  async function save(storeId: string) {
    try {
      await nmwSalesReportService.setStoreCustCode(tenantId, storeId, draft[storeId] ?? '', 'cust')
      await nmwSalesReportService.setStoreCustCode(tenantId, storeId, transferDraft[storeId] ?? '', 'transfer')
      setMsg('Saved.')
      onDone()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed')
    }
  }

  async function importLegacy() {
    try {
      const result = await nmwSalesReportService.importLegacyCustCodes(tenantId)
      setMsg(result.reason ? result.reason : `Imported ${result.imported} store code(s).`)
      await reload()
      onDone()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import failed')
    }
  }

  async function autoMatch() {
    try {
      const result = await nmwSalesReportService.autoMatchCustCodes(tenantId, true)
      const unmatched = result.unmatched?.length ? ` Unmatched: ${result.unmatched.join(', ')} (set manually).` : ''
      setMsg(result.reason ? result.reason : `Matched ${result.matched} store(s) by customer name.${unmatched}`)
      await reload()
      onDone()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Auto-match failed')
    }
  }

  return (
    <div className="card">
      <div className="card-header d-flex justify-content-between align-items-center">
        <span>Store customer codes (NMW ↔ store routing)</span>
        <div className="d-flex gap-2">
          <button className="btn btn-sm btn-primary" onClick={() => void autoMatch()}>
            Auto-match by name
          </button>
          <button className="btn btn-sm btn-outline-primary" onClick={() => void importLegacy()}>
            Import from legacy Stores
          </button>
        </div>
      </div>
      <div className="card-body">
        {msg && <div className="alert alert-success py-2 small">{msg}</div>}
        {error && <div className="alert alert-danger py-2 small">{error}</div>}
        <table className="table table-sm align-middle mb-0">
          <thead>
            <tr className="table-light">
              <th>Store</th>
              <th style={{ width: '11rem' }}>Customer code (sales)</th>
              <th style={{ width: '11rem' }}>Transfer code (TO)</th>
              <th style={{ width: '6rem' }} />
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => (
              <tr key={s.store_id}>
                <td>
                  {s.store_code} — {s.store_name}
                </td>
                <td>
                  <input
                    className="form-control form-control-sm"
                    value={draft[s.store_id] ?? ''}
                    onChange={(e) => setDraft((prev) => ({ ...prev, [s.store_id]: e.target.value }))}
                  />
                </td>
                <td>
                  <input
                    className="form-control form-control-sm"
                    value={transferDraft[s.store_id] ?? ''}
                    onChange={(e) => setTransferDraft((prev) => ({ ...prev, [s.store_id]: e.target.value }))}
                  />
                </td>
                <td>
                  <button className="btn btn-sm btn-primary" onClick={() => void save(s.store_id)}>
                    Save
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
