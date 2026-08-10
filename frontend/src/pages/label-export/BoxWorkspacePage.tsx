import { Fragment, useEffect, useState } from 'react'
import { PageHeader } from '../../components/common/PageHeader'
import { storeService } from '../../services/storeService'
import { tenantService } from '../../services/tenantService'
import { labelExporterService } from '../../services/labelExporterService'
import type { LabelBatchRow, LabelBoxProductRow, LabelBoxRow } from '../../types/labelExporter'
import type { TenantStore } from '../../types/store'
import type { Tenant } from '../../types/tenant'
import { canChangeLabelExportStore } from './labelExportAccess'
import { useAuth } from '../../hooks/useAuth'
import './label-export.css'

export default function BoxWorkspacePage() {
  const { user } = useAuth()
  const canChangeStore = canChangeLabelExportStore(user)
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [tenantId, setTenantId] = useState('')
  const [stores, setStores] = useState<TenantStore[]>([])
  const [storeId, setStoreId] = useState('')
  const [boxQuery, setBoxQuery] = useState('')
  const [startsWith, setStartsWith] = useState('')
  const [boxes, setBoxes] = useState<LabelBoxRow[]>([])
  const [selectedBox, setSelectedBox] = useState('')
  const [boxProducts, setBoxProducts] = useState<LabelBoxProductRow[]>([])
  const [expandedBoxProductCode, setExpandedBoxProductCode] = useState('')
  const [batchRowsByProduct, setBatchRowsByProduct] = useState<Record<string, LabelBatchRow[]>>({})
  const [loading, setLoading] = useState(false)
  const [boxLoading, setBoxLoading] = useState(false)
  const [loadingBatchesFor, setLoadingBatchesFor] = useState('')
  const [error, setError] = useState<string | null>(null)

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
    setBoxes([])
    setSelectedBox('')
    setBoxProducts([])
    setExpandedBoxProductCode('')
    setBatchRowsByProduct({})
  }, [tenantId, storeId])

  async function runSearch() {
    if (!tenantId || !storeId) return
    setLoading(true)
    setError(null)
    try {
      const result = await labelExporterService.searchBoxes(tenantId, storeId, boxQuery.trim(), startsWith.trim())
      const nextBoxes = Array.isArray(result?.boxes) ? result.boxes : []
      setBoxes(nextBoxes)
      const firstBox = boxQuery.trim() || nextBoxes[0]?.box_number || ''
      if (firstBox) {
        setSelectedBox(firstBox)
        void loadBoxProducts(firstBox)
      } else {
        setSelectedBox('')
        setBoxProducts([])
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load boxes')
    } finally {
      setLoading(false)
    }
  }

  async function loadBoxProducts(targetBox: string) {
    if (!tenantId || !storeId || !targetBox) return
    setBoxLoading(true)
    try {
      const result = await labelExporterService.getBoxProducts(tenantId, storeId, targetBox)
      setBoxProducts(Array.isArray(result?.rows) ? result.rows : [])
      setExpandedBoxProductCode('')
      setBatchRowsByProduct({})
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load box products')
      setBoxProducts([])
    } finally {
      setBoxLoading(false)
    }
  }

  async function loadProductBatches(productCode: string) {
    if (!tenantId || !storeId || !productCode) return
    if (batchRowsByProduct[productCode]) return
    setLoadingBatchesFor(productCode)
    try {
      const result = await labelExporterService.getProductBatches(tenantId, storeId, productCode)
      setBatchRowsByProduct((current) => ({ ...current, [productCode]: Array.isArray(result?.rows) ? result.rows : [] }))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load product batches')
      setBatchRowsByProduct((current) => ({ ...current, [productCode]: [] }))
    } finally {
      setLoadingBatchesFor('')
    }
  }

  async function toggleExpandedProduct(productCode: string) {
    if (expandedBoxProductCode === productCode) {
      setExpandedBoxProductCode('')
      return
    }
    setExpandedBoxProductCode(productCode)
    await loadProductBatches(productCode)
  }

  return (
    <div className="d-flex flex-column gap-3">
      <PageHeader title="Box Workspace" breadcrumb={['Operations', 'Inventory', 'Box Workspace']} />

      <div className="label-export-toolbar label-export-toolbar--compact">
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

        <label className="label-export-field">
          <span className="label-export-field__label">Box</span>
          <input
            className="form-control form-control-sm"
            value={boxQuery}
            onChange={(e) => setBoxQuery(e.target.value.toUpperCase())}
            placeholder="A005"
          />
        </label>

        <div className="label-export-actions-row">
          <button className="btn btn-primary btn-sm label-export-search-btn" disabled={!tenantId || !storeId || loading} onClick={() => void runSearch()}>
            {loading ? 'Loading...' : 'Search'}
          </button>
        </div>
      </div>

      {error && <div className="alert alert-danger py-2 small mb-0">{error}</div>}

      <div className="label-export-workspace">
        <section className="card shadow-sm">
          <div className="card-header">
            <strong>Boxes</strong>
          </div>
          <div className="card-body">
            <div className="label-export-panel label-export-scroll">
              <div className="label-export-box-list">
                {boxes.length === 0 ? <div className="text-muted small">Run search to load boxes</div> : boxes.map((box) => (
                  <button
                    key={box.box_number}
                    className={`label-export-box-card${selectedBox === box.box_number ? ' label-export-box-card--active' : ''}`}
                    onClick={() => {
                      setSelectedBox(box.box_number)
                      void loadBoxProducts(box.box_number)
                    }}
                  >
                    <div className="d-flex justify-content-between align-items-center">
                      <span className="fw-semibold">{box.box_number}</span>
                      <span className="label-export-box-badge">{box.product_count} products</span>
                    </div>
                    <div className="small text-muted mt-1">{box.total_stock} stock | SDay {box.best_sale_days ?? '-'} | PDay {box.best_purchase_days ?? '-'}</div>
                  </button>
                ))}
              </div>
            </div>
          </div>
        </section>

        <section className="card shadow-sm">
          <div className="card-header">
            <strong>Products {selectedBox ? `- ${selectedBox}` : ''}</strong>
          </div>
          <div className="card-body p-0">
            <div className="table-responsive label-export-scroll">
              {boxLoading ? <div className="text-muted small p-3">Loading box products...</div> : (
                <table className="table table-sm table-hover align-middle mb-0 label-export-table">
                  <thead className="table-light">
                    <tr>
                      <th>Product</th>
                      <th className="text-end">MRP</th>
                      <th className="text-end">Stock</th>
                      <th className="text-end">SDay</th>
                      <th className="text-end">PDay</th>
                    </tr>
                  </thead>
                  <tbody>
                    {boxProducts.length === 0 ? (
                      <tr><td colSpan={5} className="text-center text-muted py-4">No box selected</td></tr>
                    ) : boxProducts.map((row) => {
                      const code = row.product_code || row.product_name || ''
                      const expanded = expandedBoxProductCode === row.product_code
                      const batchRows = row.product_code ? batchRowsByProduct[row.product_code] || [] : []
                      return (
                        <Fragment key={code}>
                          <tr
                            onClick={() => row.product_code && void toggleExpandedProduct(row.product_code)}
                            className={expanded ? 'label-export-product-row-expanded' : ''}
                          >
                            <td>
                              <div className="fw-semibold">{row.product_name}</div>
                              <div className="small text-muted">{row.product_code} | {row.unit_description || '-'}</div>
                            </td>
                            <td className="text-end">{row.mrp}</td>
                            <td className="text-end">{row.total_stock}</td>
                            <td className="text-end">{row.sale_days ?? '-'}</td>
                            <td className="text-end">{row.purchase_days ?? '-'}</td>
                          </tr>
                          {expanded && (
                            <tr>
                              <td colSpan={5} className="label-export-batch-cell">
                                <div className="label-export-inline-batches">
                                  {loadingBatchesFor === row.product_code ? (
                                    <div className="label-export-inline-state text-muted small p-3">Loading batches...</div>
                                  ) : batchRows.length === 0 ? (
                                    <div className="label-export-inline-state text-muted small p-3">No batch rows found</div>
                                  ) : (
                                    <table className="table table-sm mb-0 label-export-inline-table">
                                      <thead>
                                        <tr>
                                          <th>Batch</th>
                                          <th className="text-end">Stock</th>
                                          <th>Expiry</th>
                                          <th className="text-end">MRP</th>
                                          <th className="text-end">SDay</th>
                                          <th className="text-end">PDay</th>
                                        </tr>
                                      </thead>
                                      <tbody>
                                        {batchRows.map((batch) => (
                                          <tr key={`${batch.product_code}-${batch.batch_code}-${batch.expiry_date}`} className={batch.is_expired ? 'label-expired-row' : ''}>
                                            <td>{batch.batch_code || '-'}</td>
                                            <td className="text-end">{batch.stock}</td>
                                            <td>{batch.expiry_date || '-'}</td>
                                            <td className="text-end">{batch.mrp}</td>
                                            <td className="text-end">{batch.sale_days ?? '-'}</td>
                                            <td className="text-end">{batch.purchase_days ?? '-'}</td>
                                          </tr>
                                        ))}
                                      </tbody>
                                    </table>
                                  )}
                                </div>
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      )
                    })}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}
