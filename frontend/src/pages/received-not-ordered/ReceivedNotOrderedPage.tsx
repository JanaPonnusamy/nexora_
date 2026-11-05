import { useEffect, useState } from 'react'
import { PageHeader } from '../../components/common/PageHeader'
import { ErrorState } from '../../components/common/ErrorState'
import { FilterBar } from '../../design-system/components/FilterBar'
import { legacyOrderService, type ReceivedNotOrdered } from '../../services/legacyOrderService'
import '../reports.css'

// Supplier GRN lines received since the previous active day's first order for
// products the app put on none of its orders (owner ask 2026-11-05).
// Default filter Pharma. Reads central OrderNMC, i.e. as of the last sync.
export default function ReceivedNotOrderedPage() {
  const [stores, setStores] = useState<string[]>([])
  const [store, setStore] = useState('')
  const [productType, setProductType] = useState('pharma')
  const [data, setData] = useState<ReceivedNotOrdered | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    legacyOrderService.listStores(true)
      .then((rows) => { const names = rows.map((r) => r.store_name); setStores(names); setStore((cur) => cur || names[0] || '') })
      .catch((e: Error) => setError(e.message))
  }, [])

  useEffect(() => {
    if (!store) return
    setLoading(true)
    setError(null)
    legacyOrderService.receivedNotOrdered(store, productType)
      .then(setData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [store, productType])

  const rows = data?.rows ?? []
  return (
    <div className="container-fluid px-0 rpt">
      <PageHeader title="Received, Not Ordered" breadcrumb={['Received, Not Ordered']}
        description="Supplier GRN lines since the previous active day's first order for products the app never ordered (as of the last sync)." />
      <FilterBar compact className="rpt-bar" ariaLabel="Received not ordered filters">
        <select className="form-select form-select-sm" aria-label="Store" value={store} onChange={(e) => setStore(e.target.value)}>
          {stores.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <select className="form-select form-select-sm" aria-label="Product type" value={productType} onChange={(e) => setProductType(e.target.value)}>
          <option value="pharma">Pharma</option>
          <option value="non_pharma">Non Pharma</option>
          <option value="all">All</option>
        </select>
        <span className="text-secondary small">{loading ? 'Loading…' : `${rows.length} lines${data?.since ? ` since ${new Date(data.since).toLocaleString()}` : ''}`}</span>
      </FilterBar>
      {error ? <ErrorState description={error} /> : (
        <div className="rpt-tablewrap">
          <table className="rpt-table">
            <thead>
              <tr><th>GRN</th><th>Date</th><th className="rpt-left">Supplier</th><th>Code</th><th className="rpt-left">Product</th><th>Qty</th><th>Free</th><th>PTR</th><th>MRP</th></tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={`${r.grn_no}-${r.product_code}-${i}`}>
                  <td>{r.grn_no}</td><td>{r.grn_date ? new Date(r.grn_date).toLocaleDateString() : '-'}</td>
                  <td className="rpt-left">{r.supplier_name ?? r.supplier_code ?? '-'}</td><td>{r.product_code}</td>
                  <td className="rpt-left">{r.product_name ?? '-'}</td><td>{r.qty}</td><td>{r.free_qty || ''}</td>
                  <td>{r.purchase_price.toFixed(2)}</td><td>{r.mrp.toFixed(2)}</td>
                </tr>
              ))}
              {!loading && rows.length === 0 && <tr><td colSpan={9} className="text-secondary">Nothing received outside the app's orders.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
