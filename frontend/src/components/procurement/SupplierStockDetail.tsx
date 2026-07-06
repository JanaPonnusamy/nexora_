import type { ReactNode } from 'react'
import type { SupplierStockRow, WorkspaceItem } from '../../types/procurement'
import { money, num, date } from '../stock/format'

const PRODUCT_TYPE: Record<string, string> = { '1': 'Pharma', '0': 'Non-Pharma', '2': 'Others' }

function KV({ label, value, tone }: { label: string; value: ReactNode; tone?: 'supp' | 'store' }) {
  return (
    <div className={`pm-sd__kv${tone ? ` pm-sd__kv--${tone}` : ''}`}>
      <span className="pm-sd__k">{label}</span>
      <span className="pm-sd__v">{value ?? '—'}</span>
    </div>
  )
}

/**
 * Supplier-stock-specific decision context that DetailColumn does not carry:
 * Product Summary, Inventory (supplier vs store), Commercial terms and the
 * Decision Summary. Sits above a reused DetailColumn (trend + purchase/sales
 * history + Bill Drawer), so nothing here duplicates that component. Driven by
 * the selected supplier-stock row plus its matched workspace item (by
 * product_code) — no extra API calls.
 */
export function SupplierStockDetail({
  row,
  item,
  storeStock,
  orderQty,
  supplierName,
  onWhy,
}: {
  row: SupplierStockRow
  item: WorkspaceItem | null
  storeStock: number | null
  orderQty: number | null
  supplierName: string | null
  onWhy?: () => void
}) {
  const pack = item?.pack ?? row.packing ?? null
  const unit = item?.unit_description ?? null
  const type = item?.product_type != null ? PRODUCT_TYPE[String(item.product_type)] ?? '—' : null
  const assigned = item?.assigned_qty ?? 0
  const pending = item?.remaining_qty ?? 0

  return (
    <div className="pm-sd">
      <section className="pm-sd__sec">
        <div className="pm-sd__title">Product</div>
        <div className="pm-sd__grid">
          <KV label="Product" value={row.supplier_product_name ?? row.product_name} />
          <KV label="Mapped" value={row.product_name} />
          <KV label="Code" value={row.product_code} />
          <KV label="Pack" value={pack} />
          <KV label="Unit" value={unit} />
          <KV label="Type" value={type} />
          <KV label="Supplier" value={supplierName ?? row.supplier_code} />
        </div>
      </section>

      <section className="pm-sd__sec">
        <div className="pm-sd__title">Inventory</div>
        <div className="pm-sd__grid">
          <KV label="Supplier Stock" value={num(row.available_stock ?? 0)} tone="supp" />
          <KV label="Store Stock" value={storeStock != null ? num(storeStock) : '—'} tone="store" />
          <KV label="Suggested" value={num(row.suggested_qty ?? 0)} />
          <KV label="Order Qty" value={orderQty != null ? num(orderQty) : '—'} />
          <KV label="Assigned" value={num(assigned)} />
          <KV label="Pending" value={num(pending)} />
        </div>
      </section>

      <section className="pm-sd__sec">
        <div className="pm-sd__title">Commercial</div>
        <div className="pm-sd__grid">
          <KV label="Discount" value={row.discount != null ? `${num(row.discount)}%` : '—'} />
          <KV label="Free" value={num(row.free ?? 0)} />
          <KV label="Scheme" value={row.scheme} />
          <KV label="Last Sync" value={date(row.transaction_date)} />
          <KV label="Last Purchase" value={money(item?.last_purchase_rate)} />
          <KV label="PTR" value={money(item?.ptr_cost)} />
        </div>
      </section>

      {item && (
        <section className="pm-sd__sec">
          <div className="pm-sd__title">
            Decision
            {onWhy && <button className="pm-linkbtn pm-sd__why" onClick={onWhy}>Why?</button>}
          </div>
          <div className="pm-sd__grid">
            <KV label="Stock Days" value={item.days_cover != null ? num(item.days_cover) : '—'} />
            <KV label="Movement" value={item.movement_class ?? '—'} />
            <KV label="Suggested" value={num(item.suggested_qty ?? 0)} />
            <KV label="Final" value={num(item.final_qty ?? 0)} />
          </div>
        </section>
      )}
    </div>
  )
}
