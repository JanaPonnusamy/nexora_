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

export type BillTarget = {
  kind: 'purchase' | 'sales'
  storeId: string
  billId: string
  billDate?: string | null
  productCode: string
  productName: string | null
}

type Tab = 'bill' | 'customer' | 'repeat' | 'availability'

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
  const [busyLineKey, setBusyLineKey] = useState<string | null>(null)
  const [customer, setCustomer] = useState<CustomerBillRow[] | null>(null)
  const [repeat, setRepeat] = useState<RepeatPurchaseRow[] | null>(null)
  const [avail, setAvail] = useState<AvailabilityRow[] | null>(null)

  useEffect(() => {
    let live = true
    setLoading(true)
    setBusyLineKey(null)
    setCustomer(null)
    setRepeat(null)
    setAvail(null)
    setTab('bill')
    const request =
      target.kind === 'purchase'
        ? stockService.purchaseBill(tenantId, storeId, target.billId, target.billDate).then((rows) => live && setPurchase(rows))
        : stockService.salesBill(tenantId, storeId, target.billId, target.billDate).then((rows) => live && setSales(rows))
    request
      .catch(() => {
        if (!live) return
        if (target.kind === 'purchase') setPurchase([])
        else setSales([])
      })
      .finally(() => live && setLoading(false))
    return () => { live = false }
  }, [tenantId, storeId, target.kind, target.billId, target.billDate])

  const customerCode = useMemo(
    () => (sales && sales.length > 0 ? sales[0].customer_code ?? '' : ''),
    [sales],
  )
  const hasCustomer = target.kind === 'sales' && !!customerCode && customerCode !== '0'

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
  }, [tab, customer, repeat, avail, hasCustomer, customerCode, tenantId, storeId, target.productCode])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const isPurchase = target.kind === 'purchase'
  const head = isPurchase ? purchase?.[0] : sales?.[0]
  const purchaseValue = useMemo(
    () => (purchase ?? []).reduce((sum, row) => sum + (row.qty ?? 0) * (row.ptr ?? 0), 0),
    [purchase],
  )
  const totalSalesQty = useMemo(
    () => (sales ?? []).reduce((sum, row) => sum + (row.qty ?? 0), 0),
    [sales],
  )
  const ignoredSalesLines = useMemo(
    () => (sales ?? []).filter((row) => Boolean(row.dont_consider_in_order)).length,
    [sales],
  )

  const toggleIgnoreOrder = async (row: SalesBillRow) => {
    const billDate = row.bill_date ?? target.billDate ?? ''
    const productCode = row.product_code ?? ''
    if (!billDate || !productCode) return
    const lineKey = `${productCode}|${row.batch ?? ''}`
    const nextValue = !row.dont_consider_in_order
    setBusyLineKey(lineKey)
    try {
      await stockService.setSalesBillIgnoreOrder({
        tenant_id: tenantId,
        store_id: storeId,
        bill_no: row.bill_no ?? target.billId,
        bill_date: billDate,
        product_code: productCode,
        batch: row.batch,
        dont_consider_in_order: nextValue,
      })
      setSales((prev) =>
        (prev ?? []).map((line) =>
          `${line.product_code ?? ''}|${line.batch ?? ''}` === lineKey
            ? { ...line, dont_consider_in_order: nextValue }
            : line,
        ),
      )
    } finally {
      setBusyLineKey(null)
    }
  }

  const tabs: { key: Tab; label: string; icon: string; show: boolean }[] = [
    { key: 'bill', label: 'Bill', icon: 'bi-receipt', show: true },
    { key: 'customer', label: 'Customer History', icon: 'bi-person-lines-fill', show: target.kind === 'sales' },
    { key: 'repeat', label: 'Repeat Purchase', icon: 'bi-arrow-repeat', show: true },
    { key: 'availability', label: 'Availability', icon: 'bi-box-seam', show: true },
  ]

  return (
    <>
      <div className="pm-drawer__backdrop" onClick={onClose} />
      <aside className="pm-drawer pm-drawer--wide" role="dialog" aria-modal="true" aria-label={isPurchase ? 'Purchase bill' : 'Sales bill'}>
        <header className="pm-drawer__head">
          <div>
            <h5 className="mb-0">
              <i className={`bi ${isPurchase ? 'bi-truck' : 'bi-cart-check'} me-2`} />
              {isPurchase ? 'Purchase Bill' : 'Sales Bill'} · {isPurchase ? (head as PurchaseBillRow | undefined)?.grn_no ?? target.billId : (head as SalesBillRow | undefined)?.bill_no ?? target.billId}
            </h5>
            <div className="small text-muted">{target.productName ?? target.productCode}</div>
          </div>
          <button className="btn-close" aria-label="Close" onClick={onClose} />
        </header>

        <section className="pm-info-facts pm-billhead">
          {isPurchase ? (
            <>
              <Fact label="Supplier" value={(head as PurchaseBillRow | undefined)?.supplier ?? '—'} />
              <Fact label="Bill No" value={(head as PurchaseBillRow | undefined)?.grn_no ?? '—'} />
              <Fact label="Invoice" value={(head as PurchaseBillRow | undefined)?.invoice_series ?? '—'} />
              <Fact label="Date" value={date((head as PurchaseBillRow | undefined)?.bill_date)} />
              <Fact label="Purchase Value" value={money(purchaseValue)} />
            </>
          ) : (
            <>
              <Fact label="Customer" value={(head as SalesBillRow | undefined)?.customer ?? '—'} />
              <Fact label="Bill No" value={(head as SalesBillRow | undefined)?.bill_no ?? '—'} />
              <Fact label="Date" value={date((head as SalesBillRow | undefined)?.bill_date)} />
              <Fact label="Sales Rep" value={(head as SalesBillRow | undefined)?.salesman ?? '—'} />
              <Fact label="Bill Value" value={money((head as SalesBillRow | undefined)?.bill_value)} />
              <Fact label="Bill Qty" value={num(totalSalesQty)} />
              <Fact label="Ignored Lines" value={num(ignoredSalesLines)} />
            </>
          )}
        </section>

        <nav className="pm-drawer__tabs" role="tablist">
          {tabs.filter((entry) => entry.show).map((entry) => (
            <button
              key={entry.key}
              role="tab"
              aria-selected={tab === entry.key}
              className={`pm-drawer__tab${tab === entry.key ? ' pm-drawer__tab--on' : ''}`}
              onClick={() => setTab(entry.key)}
            >
              <i className={`bi ${entry.icon}`} /> {entry.label}
            </button>
          ))}
        </nav>

        <div className="pm-drawer__body">
          {tab === 'bill' && (
            loading
              ? <Hint text="Loading bill..." />
              : isPurchase
                ? <PurchaseLines rows={purchase ?? []} />
                : <SalesLines rows={sales ?? []} busyLineKey={busyLineKey} onToggleIgnoreOrder={toggleIgnoreOrder} />
          )}
          {tab === 'customer' && (
            !hasCustomer
              ? <Hint text="No registered customer for this bill (cash sale)." />
              : customer === null
                ? <Hint text="Loading customer history..." />
                : <CustomerTab rows={customer} />
          )}
          {tab === 'repeat' && (repeat === null ? <Hint text="Loading..." /> : <RepeatTab rows={repeat} />)}
          {tab === 'availability' && (avail === null ? <Hint text="Loading availability..." /> : <AvailabilityTab rows={avail} />)}
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
      <table className="pm-minitable pm-billtable pm-billtable--purchase">
        <thead>
          <tr>
            <th>Product</th>
            <th>Batch</th>
            <th>Expiry</th>
            <th className="sx-num">Qty</th>
            <th className="sx-num">Free</th>
            <th className="sx-num">PTR</th>
            <th className="sx-num">MRP</th>
            <th className="sx-num">Tax</th>
            <th className="sx-num">Disc</th>
            <th className="sx-num">Margin</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index}>
              <td className="pm-billtable__prod">{row.product_name ?? '—'}</td>
              <td className="sx-dim">{row.batch ?? '—'}</td>
              <td className="sx-dim">{date(row.expiry)}</td>
              <td className="sx-num">{num(row.qty)}</td>
              <td className="sx-num">{num(row.free)}</td>
              <td className="sx-num">{money(row.ptr)}</td>
              <td className="sx-num">{money(row.mrp)}</td>
              <td className="sx-num">{money(row.tax)}</td>
              <td className="sx-num">{money(row.discount)}</td>
              <td className="sx-num">{row.margin != null ? `${num(row.margin)}%` : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SalesLines({
  rows,
  busyLineKey,
  onToggleIgnoreOrder,
}: {
  rows: SalesBillRow[]
  busyLineKey: string | null
  onToggleIgnoreOrder: (row: SalesBillRow) => void
}) {
  if (rows.length === 0) return <Hint text="No lines found for this bill." />
  return (
    <div className="pm-minitable-wrap">
      <table className="pm-minitable pm-billtable pm-billtable--sales">
        <thead>
          <tr>
            <th>Product</th>
            <th>Code</th>
            <th className="sx-num">Qty</th>
            <th>Batch</th>
            <th className="sx-num">MRP</th>
            <th className="sx-num">Disc</th>
            <th className="sx-num">Tax</th>
            <th className="sx-num">Next Order</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => {
            const lineKey = `${row.product_code ?? ''}|${row.batch ?? ''}`
            const saving = busyLineKey === lineKey
            return (
              <tr key={index}>
                <td className="pm-billtable__prod">{row.product_name ?? '—'}</td>
                <td className="sx-dim">{row.product_code ?? '—'}</td>
                <td className="sx-num">{num(row.qty)}</td>
                <td className="sx-dim">{row.batch || '—'}</td>
                <td className="sx-num">{money(row.mrp)}</td>
                <td className="sx-num">{row.discount != null ? `${num(row.discount)}%` : '—'}</td>
                <td className="sx-num">{money(row.tax)}</td>
                <td className="sx-num">
                  <button
                    type="button"
                    className={`pm-lineflag${row.dont_consider_in_order ? ' pm-lineflag--off' : ' pm-lineflag--on'}`}
                    disabled={saving || !row.product_code || !row.bill_date}
                    onClick={() => onToggleIgnoreOrder(row)}
                    title={
                      row.dont_consider_in_order
                        ? 'Ignored in next order calculation. Click to include again.'
                        : 'Included in next order calculation. Click to ignore this sale line.'
                    }
                  >
                    {saving ? 'Saving...' : row.dont_consider_in_order ? 'Ignored' : 'Included'}
                  </button>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function CustomerTab({ rows }: { rows: CustomerBillRow[] }) {
  if (rows.length === 0) return <Hint text="No previous bills for this customer." />
  const totalQty = rows.reduce((sum, row) => sum + (row.total_qty ?? 0), 0)
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
            {rows.map((row, index) => (
              <tr key={index}>
                <td>{row.bill_no ?? '—'}</td>
                <td className="sx-dim">{date(row.date)}</td>
                <td className="sx-num">{num(row.total_qty)}</td>
                <td className="sx-num">{money(row.bill_value)}</td>
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
          {rows.map((row, index) => (
            <tr key={index}>
              <td>{row.product_name ?? '—'}</td>
              <td className="sx-num">{num(row.times_together)}</td>
            </tr>
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
          {rows.map((row, index) => (
            <tr key={index} className={row.is_current ? 'pm-avail--cur' : ''}>
              <td>{row.store_name ?? row.store_code ?? '—'}{row.is_current ? <span className="pm-tag pm-tag--manual ms-2">this store</span> : null}</td>
              <td className="sx-num">{num(row.stock)}</td>
              <td className="sx-num">{(row.pending_qty ?? 0) > 0 ? num(row.pending_qty) : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
