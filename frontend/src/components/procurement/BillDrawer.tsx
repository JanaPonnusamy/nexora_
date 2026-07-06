import { useEffect, useMemo, useState } from 'react'
import type {
  AvailabilityRow,
  CustomerBillRow,
  PurchaseBillRow,
  RepeatPurchaseRow,
  SalesBillRow,
} from '../../types/stock'
import { stockService } from '../../services/stockService'
import { money, num, date } from '../stock/format'
import '../stock/stock-ui.css'

/** Which bill the drawer shows. Opened from a Purchase or Sales History row —
 *  the row's product is carried so the product-scoped tabs (Repeat, Availability)
 *  have context. */
export type BillTarget = {
  kind: 'purchase' | 'sales'
  storeId: string
  /** GRN number (purchase) or Bnumber (sales). */
  billId: string
  /** Bill / GRN date (disambiguates GRN numbers reused across years). */
  billDate?: string | null
  productCode: string
  productName: string | null
}

type Tab = 'bill' | 'customer' | 'repeat' | 'availability'

/** Purchase & Sales Bill Drawer with Bill / Customer History / Repeat Purchase /
 *  Availability tabs. All data comes from real synced OrderNMC tables. */
export function BillDrawer({
  tenantId,
  target,
  onClose,
}: {
  tenantId: string
  target: BillTarget
  onClose: () => void
}) {
  const storeId = target.storeId
  const [tab, setTab] = useState<Tab>('bill')

  const [purchase, setPurchase] = useState<PurchaseBillRow[] | null>(null)
  const [sales, setSales] = useState<SalesBillRow[] | null>(null)
  const [loading, setLoading] = useState(true)

  // Lazily-loaded tabs
  const [customer, setCustomer] = useState<CustomerBillRow[] | null>(null)
  const [repeat, setRepeat] = useState<RepeatPurchaseRow[] | null>(null)
  const [avail, setAvail] = useState<AvailabilityRow[] | null>(null)

  // Load the bill lines on open.
  useEffect(() => {
    let live = true
    setLoading(true)
    const p =
      target.kind === 'purchase'
        ? stockService.purchaseBill(tenantId, storeId, target.billId, target.billDate).then((r) => live && setPurchase(r))
        : stockService.salesBill(tenantId, storeId, target.billId, target.billDate).then((r) => live && setSales(r))
    p.catch(() => live && (target.kind === 'purchase' ? setPurchase([]) : setSales([]))).finally(() => live && setLoading(false))
    return () => { live = false }
  }, [tenantId, storeId, target.kind, target.billId, target.billDate])

  // The sale's customer code (from the header) — enables the Customer History tab.
  const customerCode = useMemo(
    () => (sales && sales.length > 0 ? sales[0].customer_code ?? '' : ''),
    [sales],
  )
  const hasCustomer = target.kind === 'sales' && !!customerCode && customerCode !== '0'

  // Lazy tab fetches — only when a tab is first opened.
  useEffect(() => {
    if (tab === 'customer' && customer === null && hasCustomer) {
      stockService.customerHistory(tenantId, storeId, customerCode).then(setCustomer).catch(() => setCustomer([]))
    }
    if (tab === 'repeat' && repeat === null) {
      stockService.repeatPurchase(tenantId, storeId, target.productCode).then(setRepeat).catch(() => setRepeat([]))
    }
    if (tab === 'availability' && avail === null) {
      stockService.availability(tenantId, storeId, target.productCode).then(setAvail).catch(() => setAvail([]))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, customerCode, hasCustomer])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const isPurchase = target.kind === 'purchase'
  const head = isPurchase ? purchase?.[0] : sales?.[0]
  const purchaseValue = useMemo(
    () => (purchase ?? []).reduce((a, r) => a + (r.qty ?? 0) * (r.ptr ?? 0), 0),
    [purchase],
  )

  const TABS: { key: Tab; label: string; icon: string; show: boolean }[] = [
    { key: 'bill', label: 'Bill', icon: 'bi-receipt', show: true },
    { key: 'customer', label: 'Customer History', icon: 'bi-person-lines-fill', show: target.kind === 'sales' },
    { key: 'repeat', label: 'Repeat Purchase', icon: 'bi-arrow-repeat', show: true },
    { key: 'availability', label: 'Availability', icon: 'bi-box-seam', show: true },
  ]

  return (
    <>
      <div className="pm-drawer__backdrop" onClick={onClose} />
      <aside className="pm-drawer pm-drawer--wide" role="dialog" aria-label={isPurchase ? 'Purchase bill' : 'Sales bill'}>
        <header className="pm-drawer__head">
          <div>
            <h5 className="mb-0">
              <i className={`bi ${isPurchase ? 'bi-truck' : 'bi-cart-check'} me-2`} />
              {isPurchase ? 'Purchase Bill' : 'Sales Bill'} · {isPurchase ? (head as PurchaseBillRow)?.grn_no ?? target.billId : (head as SalesBillRow)?.bill_no ?? target.billId}
            </h5>
            <div className="small text-muted">{target.productName ?? target.productCode}</div>
          </div>
          <button className="btn-close" aria-label="Close" onClick={onClose} />
        </header>

        {/* Bill header facts */}
        <section className="pm-info-facts pm-billhead">
          {isPurchase ? (
            <>
              <Fact label="Supplier" value={(head as PurchaseBillRow)?.supplier ?? '—'} />
              <Fact label="Bill No" value={(head as PurchaseBillRow)?.grn_no ?? '—'} />
              <Fact label="Invoice" value={(head as PurchaseBillRow)?.invoice_series ?? '—'} />
              <Fact label="Date" value={date((head as PurchaseBillRow)?.bill_date)} />
              <Fact label="Purchase Value" value={money(purchaseValue)} />
            </>
          ) : (
            <>
              <Fact label="Customer" value={(head as SalesBillRow)?.customer ?? '—'} />
              <Fact label="Bill No" value={(head as SalesBillRow)?.bill_no ?? '—'} />
              <Fact label="Date" value={date((head as SalesBillRow)?.bill_date)} />
              <Fact label="Sales Rep" value={(head as SalesBillRow)?.salesman ?? '—'} />
              <Fact label="Bill Value" value={money((head as SalesBillRow)?.bill_value)} />
            </>
          )}
        </section>

        <nav className="pm-drawer__tabs" role="tablist">
          {TABS.filter((t) => t.show).map((t) => (
            <button
              key={t.key}
              role="tab"
              aria-selected={tab === t.key}
              className={`pm-drawer__tab${tab === t.key ? ' pm-drawer__tab--on' : ''}`}
              onClick={() => setTab(t.key)}
            >
              <i className={`bi ${t.icon}`} /> {t.label}
            </button>
          ))}
        </nav>

        <div className="pm-drawer__body">
          {tab === 'bill' && (
            loading ? <Hint text="Loading bill…" /> : isPurchase ? <PurchaseLines rows={purchase ?? []} /> : <SalesLines rows={sales ?? []} />
          )}
          {tab === 'customer' && (
            !hasCustomer ? <Hint text="No registered customer for this bill (cash sale)." /> :
            customer === null ? <Hint text="Loading customer history…" /> : <CustomerTab rows={customer} />
          )}
          {tab === 'repeat' && (
            repeat === null ? <Hint text="Loading…" /> : <RepeatTab rows={repeat} />
          )}
          {tab === 'availability' && (
            avail === null ? <Hint text="Loading availability…" /> : <AvailabilityTab rows={avail} />
          )}
        </div>
      </aside>
    </>
  )
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="pm-info-facts__cell">
      <span className="pm-info-facts__lbl">{label}</span>
      <span className="pm-info-facts__val">{value}</span>
    </div>
  )
}
function Hint({ text }: { text: string }) {
  return <div className="pm-dsec__hint">{text}</div>
}

function PurchaseLines({ rows }: { rows: PurchaseBillRow[] }) {
  if (rows.length === 0) return <Hint text="No lines found for this GRN." />
  return (
    <div className="pm-minitable-wrap">
      <table className="pm-minitable">
        <thead>
          <tr>
            <th>Product</th><th>Batch</th><th>Expiry</th>
            <th className="sx-num">Qty</th><th className="sx-num">Free</th>
            <th className="sx-num">PTR</th><th className="sx-num">MRP</th>
            <th className="sx-num">Tax</th><th className="sx-num">Disc</th><th className="sx-num">Margin</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <td>{r.product_name ?? '—'}</td>
              <td className="sx-dim">{r.batch ?? '—'}</td>
              <td className="sx-dim">{date(r.expiry)}</td>
              <td className="sx-num">{num(r.qty)}</td>
              <td className="sx-num">{num(r.free)}</td>
              <td className="sx-num">{money(r.ptr)}</td>
              <td className="sx-num">{money(r.mrp)}</td>
              <td className="sx-num">{money(r.tax)}</td>
              <td className="sx-num">{money(r.discount)}</td>
              <td className="sx-num">{r.margin != null ? `${num(r.margin)}%` : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SalesLines({ rows }: { rows: SalesBillRow[] }) {
  if (rows.length === 0) return <Hint text="No lines found for this bill." />
  return (
    <div className="pm-minitable-wrap">
      <table className="pm-minitable">
        <thead>
          <tr>
            <th>Product</th><th className="sx-num">Qty</th><th>Batch</th>
            <th className="sx-num">MRP</th><th className="sx-num">Disc</th><th className="sx-num">Tax</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              <td>{r.product_name ?? '—'}</td>
              <td className="sx-num">{num(r.qty)}</td>
              <td className="sx-dim">{r.batch || '—'}</td>
              <td className="sx-num">{money(r.mrp)}</td>
              <td className="sx-num">{r.discount != null ? `${num(r.discount)}%` : '—'}</td>
              <td className="sx-num">{money(r.tax)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function CustomerTab({ rows }: { rows: CustomerBillRow[] }) {
  if (rows.length === 0) return <Hint text="No previous bills for this customer." />
  const totalQty = rows.reduce((a, r) => a + (r.total_qty ?? 0), 0)
  const avgQty = rows.length ? totalQty / rows.length : 0
  return (
    <>
      <section className="pm-info-facts">
        <Fact label="Bills (recent)" value={num(rows.length)} />
        <Fact label="Avg Qty / Bill" value={avgQty.toFixed(1)} />
        <Fact label="Last Purchase" value={date(rows[0].date)} />
        <Fact label="Last Bill Value" value={money(rows[0].bill_value)} />
      </section>
      <div className="pm-minitable-wrap">
        <table className="pm-minitable">
          <thead><tr><th>Bill No</th><th>Date</th><th className="sx-num">Qty</th><th className="sx-num">Value</th></tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td>{r.bill_no ?? '—'}</td>
                <td className="sx-dim">{date(r.date)}</td>
                <td className="sx-num">{num(r.total_qty)}</td>
                <td className="sx-num">{money(r.bill_value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

function RepeatTab({ rows }: { rows: RepeatPurchaseRow[] }) {
  if (rows.length === 0) return <Hint text="No frequently-bought-together products found." />
  return (
    <div className="pm-minitable-wrap">
      <table className="pm-minitable">
        <thead><tr><th>Usually Bought Together</th><th className="sx-num">Times</th></tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}><td>{r.product_name ?? '—'}</td><td className="sx-num">{num(r.times_together)}</td></tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function AvailabilityTab({ rows }: { rows: AvailabilityRow[] }) {
  if (rows.length === 0) return <Hint text="No stock information across stores." />
  return (
    <div className="pm-minitable-wrap">
      <table className="pm-minitable">
        <thead>
          <tr><th>Store</th><th className="sx-num">Current Stock</th><th className="sx-num">On Order</th></tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className={r.is_current ? 'pm-avail--cur' : ''}>
              <td>{r.store_name ?? r.store_code ?? '—'}{r.is_current ? <span className="pm-tag pm-tag--manual ms-2">this store</span> : null}</td>
              <td className="sx-num">{num(r.stock)}</td>
              <td className="sx-num">{(r.pending_qty ?? 0) > 0 ? num(r.pending_qty) : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
