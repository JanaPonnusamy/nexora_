import { Fragment, useCallback, useEffect, useMemo, useState } from 'react'
import { PageHeader } from '../../components/common/PageHeader'
import { tenantService } from '../../services/tenantService'
import { storeService } from '../../services/storeService'
import { nmwSalesReportService } from '../../services/nmwSalesReportService'
import type { Tenant } from '../../types/tenant'
import type { TenantStore } from '../../types/store'
import type {
  NmwPurchaseEntry,
  NmwSalesBill,
  NmwSalesBillItem,
  NmwSalesBillSummary,
  PurchaseStatusFilter,
} from '../../types/nmwSalesReport'
import { FilterBar } from '../../design-system/components/FilterBar'
import { exportNmwBillCsv, exportNmwBillExcel, purchaseStatusLabel } from './exportNmwBill'

type StatusFilter = 'all' | 'pending' | 'approved'

type PurchaseEntryState =
  | { kind: 'loading' }
  | { kind: 'loaded'; data: NmwPurchaseEntry }
  | { kind: 'error' }

const PURCHASE_BADGE_CLASS: Record<string, string> = {
  completed: 'text-bg-success',
  pending: 'text-bg-warning',
  not_found: 'text-bg-danger',
  error: 'text-bg-secondary',
}

function purchaseBadge(status: string) {
  return (
    <span className={`badge ${PURCHASE_BADGE_CLASS[status] ?? 'text-bg-secondary'}`}>
      {purchaseStatusLabel(status as never) || 'Unknown'}
    </span>
  )
}

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
  const [purchaseStatusFilter, setPurchaseStatusFilter] = useState<PurchaseStatusFilter>('all')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [purchaseStatusError, setPurchaseStatusError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [bills, setBills] = useState<NmwSalesBill[]>([])
  const [canApprove, setCanApprove] = useState(false)
  const [scope, setScope] = useState<'store' | 'all'>('store')

  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [expanded, setExpanded] = useState<string | null>(null)
  const [items, setItems] = useState<Record<string, NmwSalesBillItem[]>>({})
  const [summaries, setSummaries] = useState<Record<string, NmwSalesBillSummary | null>>({})
  const [purchaseEntries, setPurchaseEntries] = useState<Record<string, PurchaseEntryState>>({})
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
    setPurchaseStatusError(null)
    setNotice(null)
    setSelected(new Set())
    setExpanded(null)
    try {
      const result = await nmwSalesReportService.listBills(tenantId, {
        storeId: storeId || undefined,
        status,
        dateFrom: dateFrom || undefined,
        dateTo: dateTo || undefined,
        purchaseStatus: purchaseStatusFilter,
      })
      setBills(result.bills)
      setCanApprove(result.can_approve)
      setScope(result.scope)
      setPurchaseStatusError(result.purchase_status_error ?? null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load bills')
      setBills([])
    } finally {
      setLoading(false)
    }
  }, [tenantId, storeId, status, purchaseStatusFilter, dateFrom, dateTo])

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
        setSummaries((prev) => ({ ...prev, [key]: result.summary }))
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load bill items')
      }
    }
    if (!purchaseEntries[key] && bill.bill_no && bill.bill_date) {
      setPurchaseEntries((prev) => ({ ...prev, [key]: { kind: 'loading' } }))
      try {
        const data = await nmwSalesReportService.purchaseEntry(tenantId, bill.bill_no, bill.bill_date)
        setPurchaseEntries((prev) => ({ ...prev, [key]: { kind: 'loaded', data } }))
      } catch {
        // A failed lookup is a distinct state from "not found" -- the bill row
        // itself still shows whatever purchase_status the batched list query
        // returned (never overwritten here), this only affects the detail panel.
        setPurchaseEntries((prev) => ({ ...prev, [key]: { kind: 'error' } }))
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

  const [bulkCutoff, setBulkCutoff] = useState('2026-08-01')

  async function approveBefore() {
    if (!bulkCutoff) return
    setLoading(true)
    setError(null)
    try {
      const result = await nmwSalesReportService.approveBefore(tenantId, bulkCutoff)
      setNotice(`Approved ${result.approved} bill(s) dated before ${result.cutoff}.`)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Bulk approval failed')
    } finally {
      setLoading(false)
    }
  }

  async function reconcile() {
    setLoading(true)
    setError(null)
    try {
      // Preview first so the count is shown; apply only if there is something to clean.
      const preview = await nmwSalesReportService.reconcile(tenantId, false)
      if (preview.orphan_rows === 0) {
        setNotice('Mirror already matches the source — no duplicate lines to remove.')
        return
      }
      const ok = window.confirm(
        `Remove ${preview.orphan_rows} duplicate line(s) across ${preview.affected_bills} modified bill(s)?\n` +
          `These are old lines the store POS replaced when a bill was edited.` +
          (preview.skipped_lag_bills.length
            ? `\n\n${preview.skipped_lag_bills.length} bill(s) are still syncing their latest version and will be skipped.`
            : ''),
      )
      if (!ok) return
      const result = await nmwSalesReportService.reconcile(tenantId, true)
      setNotice(`Removed ${result.deleted} duplicate line(s) from ${result.affected_bills} bill(s).`)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Reconcile failed')
    } finally {
      setLoading(false)
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

      <FilterBar compact className="align-items-end" ariaLabel="NMW sales filters">
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

        {scope === 'all' && (
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
        )}

        <label className="d-flex flex-column gap-1">
          <span className="small text-muted">Status</span>
          <select className="form-select" value={status} onChange={(e) => setStatus(e.target.value as StatusFilter)}>
            <option value="all">All</option>
            <option value="pending">Pending</option>
            <option value="approved">Approved</option>
          </select>
        </label>

        <label className="d-flex flex-column gap-1">
          <span className="small text-muted">Purchase entry</span>
          <select
            className="form-select"
            value={purchaseStatusFilter}
            onChange={(e) => setPurchaseStatusFilter(e.target.value as PurchaseStatusFilter)}
          >
            <option value="all">All</option>
            <option value="completed">Completed</option>
            <option value="pending">Pending</option>
            <option value="not_found">Not Found</option>
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
            <button
              className="btn btn-outline-danger"
              disabled={loading}
              title="Remove duplicate bill lines left behind when a bill was modified at the store"
              onClick={() => void reconcile()}
            >
              <i className="bi bi-recycle me-1" />
              Reconcile duplicates
            </button>
            <div className="input-group" style={{ width: 'auto' }}>
              <span className="input-group-text">Approve all before</span>
              <input type="date" className="form-control" style={{ maxWidth: '10rem' }} value={bulkCutoff} onChange={(e) => setBulkCutoff(e.target.value)} />
              <button className="btn btn-warning" disabled={loading || !bulkCutoff} onClick={() => void approveBefore()}>
                Approve
              </button>
            </div>
          </>
        )}
      </FilterBar>

      {scope === 'store' && (
        <div className="alert alert-secondary py-2 small mb-0">
          You are viewing only your own store's approved bills.
        </div>
      )}
      {notice && <div className="alert alert-success py-2 small mb-0">{notice}</div>}
      {error && <div className="alert alert-danger py-2 small mb-0">{error}</div>}
      {purchaseStatusError && (
        <div className="alert alert-warning py-2 small mb-0">
          {purchaseStatusError} Sales bill data below is unaffected; the Purchase Entry column may be unavailable until this is retried.
        </div>
      )}

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
                <th style={{ whiteSpace: 'nowrap' }}>Purchase Entry</th>
                <th style={{ whiteSpace: 'nowrap' }} />
              </tr>
            </thead>
            <tbody>
              {bills.map((bill) => {
                const key = billKey(bill)
                const isApproved = bill.status === 'approved'
                return (
                  <Fragment key={key}>
                    <tr className={bill.is_cancelled ? 'text-danger' : undefined}>
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
                      <td style={{ whiteSpace: 'nowrap' }}>
                        {purchaseBadge(bill.purchase_status)}
                        {bill.purchase_status === 'completed' && bill.purchase_entry_no && (
                          <span className="text-muted ms-1 small" title="Store GRN number">
                            GRN {bill.purchase_entry_no}
                          </span>
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
                        <td colSpan={canApprove ? 11 : 10} className="p-0">
                          <BillDetailPanel
                            bill={bill}
                            items={items[key]}
                            summary={summaries[key]}
                            purchaseEntry={purchaseEntries[key]}
                          />
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

function BillDetailPanel({
  bill,
  items: rows,
  summary,
  purchaseEntry,
}: {
  bill: NmwSalesBill
  items: NmwSalesBillItem[] | undefined
  summary?: NmwSalesBillSummary | null
  purchaseEntry: PurchaseEntryState | undefined
}) {
  const purchaseEntryFailed = purchaseEntry?.kind === 'error'
  const purchaseEntryData = purchaseEntry?.kind === 'loaded' ? purchaseEntry.data : null

  function doExport(kind: 'csv' | 'xlsx') {
    const exportData = { bill, items: rows ?? [], purchaseEntry: purchaseEntryData, purchaseEntryFailed }
    const fileName = `NMW_${bill.bill_no ?? 'bill'}`
    if (kind === 'csv') exportNmwBillCsv(exportData, fileName)
    else void exportNmwBillExcel(exportData, fileName)
  }

  return (
    <div className="p-2">
      <div className="d-flex justify-content-between align-items-start flex-wrap gap-3 mb-2">
        <div className="d-flex flex-wrap gap-4">
          <div>
            <div className="small text-muted text-uppercase fw-semibold">Sales Bill</div>
            <div className="small">
              Bill No: <strong>{bill.bill_no}</strong>
            </div>
            <div className="small">Date: {bill.bill_date}</div>
            <div className="small">Store: {bill.dest_store_code}</div>
            <div className="small">Amount: {money(bill.bill_amount)}</div>
            <div className="small">
              Sales Status:{' '}
              {bill.status === 'approved' ? (
                <span className="badge text-bg-success">Approved</span>
              ) : (
                <span className="badge text-bg-warning">Pending</span>
              )}
            </div>
          </div>
          <div>
            <div className="small text-muted text-uppercase fw-semibold">Purchase Entry</div>
            {!purchaseEntry || purchaseEntry.kind === 'loading' ? (
              <div className="small text-muted">Checking…</div>
            ) : purchaseEntry.kind === 'error' ? (
              <div className="small text-danger">Unable to check purchase entry right now.</div>
            ) : (
              <>
                <div className="small">
                  Status: {purchaseBadge(purchaseEntry.data.purchase_status)}
                  {purchaseEntry.data.total_products > 0 && (
                    <span className="text-muted ms-2">
                      Received {purchaseEntry.data.matched_products} of {purchaseEntry.data.total_products} item(s)
                    </span>
                  )}
                </div>
                <div className="small">GRN No: {purchaseEntry.data.entry_no ?? '—'}</div>
                <div className="small">Entry Date: {purchaseEntry.data.entry_date ?? '—'}</div>
                {purchaseEntry.data.match_basis === 'bill_number' && (
                  <div className="small text-muted">
                    Matched by bill number{purchaseEntry.data.grn_amount != null && (
                      <> · Bill {money(bill.bill_amount)} vs GRN {money(purchaseEntry.data.grn_amount)}</>
                    )}
                  </div>
                )}
                {purchaseEntry.data.pending_products.length > 0 && (
                  <div className="small mt-1">
                    <span className="text-danger fw-semibold">Not yet entered:</span>
                    <ul className="mb-0 ps-3">
                      {purchaseEntry.data.pending_products.map((p) => (
                        <li key={p.product_code}>
                          {p.product_name} <span className="text-muted">(need {p.required_qty}, got {p.received_qty})</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
        <div className="d-flex gap-2">
          <button className="btn btn-sm btn-outline-secondary" onClick={() => doExport('csv')} title="Export this bill as CSV">
            <i className="bi bi-filetype-csv me-1" />
            CSV
          </button>
          <button className="btn btn-sm btn-outline-secondary" onClick={() => doExport('xlsx')} title="Export this bill as XLSX">
            <i className="bi bi-file-earmark-excel me-1" />
            XLSX
          </button>
        </div>
      </div>
      <BillItemsTable rows={rows} summary={summary} />
    </div>
  )
}

function BillItemsTable({
  rows,
  summary,
}: {
  rows: NmwSalesBillItem[] | undefined
  summary?: NmwSalesBillSummary | null
}) {
  if (!rows) return <div className="p-2 small text-muted">Loading items…</div>
  if (rows.length === 0) return <div className="p-2 small text-muted">No line items.</div>
  // Amount column is the 9th (index 8): Product, Batch, Expiry, Qty, Free, MRP,
  // Rate, Dis%, Amount. The footer labels span the first 8, value sits under it.
  const labelSpan = 8
  const footerRow = (label: string, value: number, opts: { bold?: boolean } = {}) => (
    <tr className={opts.bold ? 'fw-semibold border-top' : undefined}>
      <td colSpan={labelSpan} className="text-end text-muted">
        {label}
      </td>
      <td className="text-end" style={{ whiteSpace: 'nowrap' }}>
        {money(value)}
      </td>
    </tr>
  )
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
      {summary && (
        <tfoot>
          {footerRow('Sub-total', summary.subtotal)}
          {summary.cgst > 0 && footerRow('CGST', summary.cgst)}
          {summary.sgst > 0 && footerRow('SGST', summary.sgst)}
          {Math.abs(summary.roundoff) >= 0.005 && footerRow('Round-off', summary.roundoff)}
          {footerRow('Bill Amount', summary.bill_amount, { bold: true })}
        </tfoot>
      )}
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
