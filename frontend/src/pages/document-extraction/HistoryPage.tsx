import { useCallback, useEffect, useMemo, useState } from 'react'
import { PageHeader } from '../../components/common/PageHeader'
import { UniGrid, type UniGridColumn } from '../../platform/ui'
import { HistoryDetailPanel } from '../../components/document-extraction/HistoryDetailPanel'
import { documentExtractionService } from '../../services/documentExtractionService'
import { storeService } from '../../services/storeService'
import type { ImportListRow } from '../../types/documentExtraction'
import type { Store } from '../../types/store'

export default function DocumentExtractionHistoryPage() {
  const [stores, setStores] = useState<Store[]>([])
  const [storeId, setStoreId] = useState('')
  const [invoiceNumber, setInvoiceNumber] = useState('')
  const [supplierName, setSupplierName] = useState('')
  const [status, setStatus] = useState('')
  const [imports, setImports] = useState<ImportListRow[]>([])
  const [total, setTotal] = useState(0)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [isLoading, setIsLoading] = useState(false)

  useEffect(() => {
    storeService.list().then((all) => setStores(all.filter((s) => s.is_active))).catch(() => setStores([]))
  }, [])

  useEffect(() => {
    if (!storeId && stores.length > 0) setStoreId(stores[0].store_id)
  }, [stores, storeId])

  const tenantId = useMemo(
    () => stores.find((s) => s.store_id === storeId)?.tenant_id ?? '',
    [stores, storeId],
  )

  const loadImports = useCallback(() => {
    if (!tenantId) return
    setIsLoading(true)
    documentExtractionService.listImports(tenantId, storeId)
      .then((page) => {
        // Client-side filter — the module's own filter set (status/supplier/invoice)
        // is already server-side on GET /imports; kept simple here since History's
        // job is showing what's already there, not a new search feature.
        let rows = page.items
        if (status) rows = rows.filter((r) => r.status === status)
        if (invoiceNumber) rows = rows.filter((r) => (r.invoice_number ?? '').toLowerCase().includes(invoiceNumber.toLowerCase()))
        if (supplierName) rows = rows.filter((r) => (r.supplier_name ?? '').toLowerCase().includes(supplierName.toLowerCase()))
        setImports(rows)
        setTotal(page.total)
      })
      .catch(() => setImports([]))
      .finally(() => setIsLoading(false))
  }, [tenantId, storeId, status, invoiceNumber, supplierName])

  useEffect(() => { loadImports() }, [loadImports])

  const columns: UniGridColumn<ImportListRow>[] = [
    { key: 'import_id', header: 'ID', width: '4rem' },
    { key: 'invoice_number', header: 'Invoice #', render: (r) => r.invoice_number ?? '—' },
    {
      key: 'supplier_name', header: 'Supplier',
      render: (r) => (
        <>
          {r.supplier_name ?? '—'}
          {r.is_supplier_unknown && <span className="badge text-bg-warning ms-1">Unknown</span>}
        </>
      ),
    },
    { key: 'status', header: 'Status' },
    {
      key: 'validation_status', header: 'Validation',
      render: (r) => (
        <span className={`badge ${r.validation_status === 'FAILED' ? 'text-bg-danger' : r.validation_status === 'WARNING' ? 'text-bg-warning' : 'text-bg-secondary'}`}>
          {r.validation_status}
        </span>
      ),
    },
    { key: 'net_amount', header: 'Net Amount', align: 'end', render: (r) => r.net_amount ?? '—' },
    { key: 'uploaded_at', header: 'Uploaded', render: (r) => new Date(r.uploaded_at).toLocaleString() },
  ]

  return (
    <div className="container-fluid px-0">
      <PageHeader title="Document Extraction — History" breadcrumb={['Document Extraction', 'History']} />

      <div className="row g-2 mb-3">
        <div className="col-auto">
          <label className="form-label small mb-0">Store</label>
          <select className="form-select form-select-sm" value={storeId} onChange={(e) => setStoreId(e.target.value)}>
            {stores.map((s) => (
              <option key={s.store_id} value={s.store_id}>{s.store_code} — {s.store_name}</option>
            ))}
          </select>
        </div>
        <div className="col-auto">
          <label className="form-label small mb-0">Invoice #</label>
          <input className="form-control form-control-sm" value={invoiceNumber} onChange={(e) => setInvoiceNumber(e.target.value)} />
        </div>
        <div className="col-auto">
          <label className="form-label small mb-0">Supplier</label>
          <input className="form-control form-control-sm" value={supplierName} onChange={(e) => setSupplierName(e.target.value)} />
        </div>
        <div className="col-auto">
          <label className="form-label small mb-0">Status</label>
          <select className="form-select form-select-sm" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All</option>
            <option value="UPLOADED">Uploaded</option>
            <option value="EXTRACTED">Extracted</option>
            <option value="REVIEW_PENDING">Review Pending</option>
            <option value="SAVED">Saved</option>
            <option value="EXPORTED">Exported</option>
            <option value="FAILED">Failed</option>
          </select>
        </div>
      </div>

      <p className="text-muted small">{total} invoice(s)</p>

      <UniGrid
        columns={columns}
        rows={imports}
        getRowId={(r) => String(r.import_id)}
        isLoading={isLoading}
        onRowClick={(r) => setSelectedId(r.import_id)}
        activeRowId={selectedId != null ? String(selectedId) : undefined}
        emptyTitle="No invoices"
        emptyDescription="No invoices match the current filters for this store."
      />

      {selectedId != null && (
        <div className="mt-3">
          <HistoryDetailPanel importId={selectedId} onChanged={loadImports} />
        </div>
      )}
    </div>
  )
}
