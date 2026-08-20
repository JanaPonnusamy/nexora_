import { useCallback, useEffect, useMemo, useState } from 'react'
import { PageHeader } from '../../components/common/PageHeader'
import { HistoryDetailPanel } from '../../components/document-extraction/HistoryDetailPanel'
import { documentExtractionService } from '../../services/documentExtractionService'
import { storeService } from '../../services/storeService'
import type { ImportListRow } from '../../types/documentExtraction'
import type { Store } from '../../types/store'
import { AppDataGrid, type AppDataGridColumn } from '../../design-system/components/AppDataGrid'
import { InspectorPanel } from '../../design-system/components/InspectorPanel'
import { SplitView } from '../../design-system/components/SplitView'
import { WorkspaceShell } from '../../design-system/components/WorkspaceShell'
import { FilterBar, FilterSearch, FilterSelect } from '../../design-system/components/FilterBar'

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
    storeService.list().then((all) => setStores(all.filter((store) => store.is_active))).catch(() => setStores([]))
  }, [])

  useEffect(() => {
    if (!storeId && stores.length > 0) setStoreId(stores[0].store_id)
  }, [stores, storeId])

  const tenantId = useMemo(
    () => stores.find((store) => store.store_id === storeId)?.tenant_id ?? '',
    [stores, storeId],
  )

  const loadImports = useCallback(() => {
    if (!tenantId) return
    setIsLoading(true)
    documentExtractionService.listImports(tenantId, storeId)
      .then((page) => {
        let rows = page.items
        if (status) rows = rows.filter((row) => row.status === status)
        if (invoiceNumber) rows = rows.filter((row) => (row.invoice_number ?? '').toLowerCase().includes(invoiceNumber.toLowerCase()))
        if (supplierName) rows = rows.filter((row) => (row.supplier_name ?? '').toLowerCase().includes(supplierName.toLowerCase()))
        setImports(rows)
        setTotal(page.total)
      })
      .catch(() => setImports([]))
      .finally(() => setIsLoading(false))
  }, [tenantId, storeId, status, invoiceNumber, supplierName])

  useEffect(() => {
    loadImports()
  }, [loadImports])

  const columns: AppDataGridColumn<ImportListRow>[] = [
    { key: 'import_id', header: 'ID', width: '4rem' },
    { key: 'invoice_number', header: 'Invoice #', sticky: true, render: (row) => row.invoice_number ?? '-' },
    {
      key: 'supplier_name',
      header: 'Supplier',
      render: (row) => (
        <>
          {row.supplier_name ?? '-'}
          {row.is_supplier_unknown && <span className="badge text-bg-warning ms-1">Unknown</span>}
        </>
      ),
    },
    { key: 'status', header: 'Status' },
    {
      key: 'validation_status',
      header: 'Validation',
      render: (row) => (
        <span className={`badge ${row.validation_status === 'FAILED' ? 'text-bg-danger' : row.validation_status === 'WARNING' ? 'text-bg-warning' : 'text-bg-secondary'}`}>
          {row.validation_status}
        </span>
      ),
    },
    { key: 'net_amount', header: 'Net Amount', align: 'end', render: (row) => row.net_amount ?? '-' },
    { key: 'uploaded_at', header: 'Uploaded', render: (row) => new Date(row.uploaded_at).toLocaleString() },
  ]

  return (
    <WorkspaceShell
      fullWidth
      header={
        <PageHeader
          title="Document Extraction History"
          breadcrumb={['Operations', 'Document Extraction', 'History']}
          description="Review processed invoices, filter by store or supplier, and inspect saved document details without leaving the workspace."
        />
      }
      filters={
        <FilterBar ariaLabel="Invoice history filters">
          <FilterSelect className="list-toolbar__filter" value={storeId} onChange={setStoreId} ariaLabel="Store">
            {stores.map((store) => (
              <option key={store.store_id} value={store.store_id}>{store.store_code} - {store.store_name}</option>
            ))}
          </FilterSelect>
          <FilterSearch
            icon="bi-receipt"
            value={invoiceNumber}
            placeholder="Search invoice number"
            ariaLabel="Search invoice number"
            onChange={setInvoiceNumber}
          />
          <FilterSearch
            icon="bi-building"
            value={supplierName}
            placeholder="Search supplier"
            ariaLabel="Search supplier"
            onChange={setSupplierName}
          />
          <FilterSelect className="list-toolbar__filter" value={status} onChange={setStatus} ariaLabel="Status">
            <option value="">All statuses</option>
            <option value="UPLOADED">Uploaded</option>
            <option value="EXTRACTED">Extracted</option>
            <option value="REVIEW_PENDING">Review Pending</option>
            <option value="SAVED">Saved</option>
            <option value="EXPORTED">Exported</option>
            <option value="FAILED">Failed</option>
          </FilterSelect>
        </FilterBar>
      }
      statusBar={
        <>
          <span>{total.toLocaleString()} invoice(s)</span>
          <span>{imports.length.toLocaleString()} loaded</span>
          <span>{selectedId != null ? `Inspecting #${selectedId}` : 'Select an invoice to inspect details'}</span>
        </>
      }
    >
      <SplitView
        primary={
          <AppDataGrid
            title="Invoice History"
            storageKey="document-extraction-history"
            columns={columns}
            rows={imports}
            getRowId={(row) => String(row.import_id)}
            isLoading={isLoading}
            onRowClick={(row) => setSelectedId(row.import_id)}
            activeRowId={selectedId != null ? String(selectedId) : undefined}
            emptyTitle="No invoices"
            emptyDescription="No invoices match the current filters for this store."
            pageSize={20}
          />
        }
        secondary={
          <InspectorPanel
            title="Invoice Inspector"
            summary={selectedId != null ? `Import #${selectedId}` : 'Choose an invoice from the grid'}
            empty={selectedId == null}
          >
            {selectedId != null && <HistoryDetailPanel importId={selectedId} onChanged={loadImports} />}
          </InspectorPanel>
        }
      />
    </WorkspaceShell>
  )
}
