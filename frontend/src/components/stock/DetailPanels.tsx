import { useCallback } from 'react'
import type { ProductContext, SalesRow } from '../../types/stock'
import { stockService } from '../../services/stockService'
import { EmptyState } from '../common/EmptyState'
import { ErrorState } from '../common/ErrorState'
import { TableSkeleton } from '../common/TableSkeleton'
import { SxCard, SxCardHead, SxCardBody, SxTable, SxChip } from '../sync/ui'
import { useStockResource } from './useStockResource'
import { MovementChart } from './MovementChart'
import { money, num, date } from './format'

function panelKey(ctx: ProductContext | null): string | null {
  return ctx ? `${ctx.tenantId}|${ctx.storeId}|${ctx.productCode}` : null
}

/* ---- Product context bar (single row) ------------------------------------ */

export function ProductContextBar({ ctx }: { ctx: ProductContext }) {
  const fetcher = useCallback(
    () => stockService.productDetails(ctx.tenantId, ctx.storeId, ctx.productCode),
    [ctx.tenantId, ctx.storeId, ctx.productCode],
  )
  const { data } = useStockResource(fetcher, panelKey(ctx), 'product-details')
  const stock = data?.total_stock ?? ctx.stock

  return (
    <div className="sa-ctx">
      <div className="sa-ctx__lead">
        <i className="bi bi-box-seam" aria-hidden="true" />
        <strong>{ctx.productName ?? ctx.productCode}</strong>
        <span className="sa-tag">{ctx.storeCode ?? ctx.storeName}</span>
        <span className="sa-tag sa-tag--stock">
          <span className={`sa-dot sa-dot--${stock > 0 ? 'in' : 'out'}`} aria-hidden="true" />
          Stock {num(stock)}
        </span>
      </div>
      <div className="sa-ctx__stats">
        <span className="sa-ctx__stat"><b>MRP</b>{money(data?.mrp)}</span>
        <span className="sa-ctx__stat"><b>Sale Unit</b>{data?.sale_unit ?? '—'}</span>
        <span className="sa-ctx__stat"><b>Packing</b>{data?.packing != null ? num(data.packing) : '—'}</span>
        <span className="sa-ctx__stat"><b>Sub-Loc</b>{data?.sublocation ?? '—'}</span>
        <span className="sa-ctx__stat"><b>Last Sale</b>{date(data?.last_sale)}</span>
        <span className="sa-ctx__stat"><b>Last Purchase</b>{date(data?.last_purchase)}</span>
      </div>
    </div>
  )
}

/* ---- Monthly Movement ---------------------------------------------------- */

export function MovementPanel({ ctx }: { ctx: ProductContext }) {
  // Always the last 4 months; empty months are shown as blank bars.
  const fetcher = useCallback(
    () => stockService.monthlyMovement(ctx.tenantId, ctx.storeId, ctx.productCode, 4),
    [ctx.tenantId, ctx.storeId, ctx.productCode],
  )
  const { data, isLoading, error, reload } = useStockResource(fetcher, panelKey(ctx), 'movement')

  return (
    <SxCard className="sa-chart-card">
      <SxCardHead title="Monthly Movement" icon="bi-bar-chart-line" sub="Last 4 months" />
      <SxCardBody>
        {isLoading ? (
          <TableSkeleton rows={4} columns={3} />
        ) : error ? (
          <ErrorState description={error} onRetry={reload} />
        ) : !data || data.length === 0 ? (
          <EmptyState icon="bi-bar-chart" title="No movement" description="No transaction movement found." />
        ) : (
          <MovementChart rows={data} />
        )}
      </SxCardBody>
    </SxCard>
  )
}

/* ---- Batch Details ------------------------------------------------------- */

export function BatchPanel({ ctx }: { ctx: ProductContext }) {
  const fetcher = useCallback(
    () => stockService.batchDetails(ctx.tenantId, ctx.storeId, ctx.productCode),
    [ctx.tenantId, ctx.storeId, ctx.productCode],
  )
  const { data, isLoading, error, reload } = useStockResource(fetcher, panelKey(ctx), 'batch')

  return (
    <SxCard>
      <SxCardHead title="Batch Details" icon="bi-layers" />
      <SxCardBody flush>
        {isLoading ? (
          <div className="p-3"><TableSkeleton rows={4} columns={6} /></div>
        ) : error ? (
          <ErrorState description={error} onRetry={reload} />
        ) : !data || data.length === 0 ? (
          <EmptyState icon="bi-layers" title="No batches" description="No batch stock found." />
        ) : (
          <SxTable>
            <colgroup>
              <col style={{ width: '84px' }} /><col style={{ width: '56px' }} /><col style={{ width: '74px' }} />
              <col style={{ width: '62px' }} /><col /><col />
            </colgroup>
            <thead>
              <tr>
                <th>Batch No.</th><th className="sx-num">Stock</th><th>Expiry</th>
                <th>Age</th><th className="sx-num">PTR</th><th className="sx-num">MRP</th>
              </tr>
            </thead>
            <tbody>
              {data.map((row, i) => (
                <tr key={`${row.batch_no}-${i}`}>
                  <td>{row.batch_no ?? '—'}</td>
                  <td className="sx-num">{num(row.stock)}</td>
                  <td className="sx-dim">{date(row.expiry_date)}</td>
                  <td className="sx-dim">{row.age ?? '—'}</td>
                  <td className="sx-num">{money(row.ptr)}</td>
                  <td className="sx-num">{money(row.mrp)}</td>
                </tr>
              ))}
            </tbody>
          </SxTable>
        )}
      </SxCardBody>
    </SxCard>
  )
}

/* ---- Recent Sales -------------------------------------------------------- */

export function SalesPanel({
  ctx, onSelect, activeBillNo,
}: {
  ctx: ProductContext
  onSelect?: (row: SalesRow) => void
  activeBillNo?: string | null
}) {
  const fetcher = useCallback(
    () => stockService.salesHistory(ctx.tenantId, ctx.storeId, ctx.productCode),
    [ctx.tenantId, ctx.storeId, ctx.productCode],
  )
  const { data, isLoading, error, reload } = useStockResource(fetcher, panelKey(ctx), 'sales')

  return (
    <SxCard>
      <SxCardHead title="Recent Sales" icon="bi-cart-check" />
      <SxCardBody flush>
        {isLoading ? (
          <div className="p-3"><TableSkeleton rows={4} columns={6} /></div>
        ) : error ? (
          <ErrorState description={error} onRetry={reload} />
        ) : !data || data.length === 0 ? (
          <EmptyState icon="bi-cart" title="No sales" description="No recent sales found." />
        ) : (
          <SxTable>
            <colgroup>
              <col style={{ width: '78px' }} /><col style={{ width: '92px' }} /><col />
              <col style={{ width: '46px' }} /><col style={{ width: '66px' }} /><col style={{ width: '54px' }} />
            </colgroup>
            <thead>
              <tr>
                <th>Date</th><th>Bill No.</th><th>Customer</th>
                <th className="sx-num">Qty</th><th className="sx-num">MRP</th><th className="sx-num">Disc</th>
              </tr>
            </thead>
            <tbody>
              {data.map((row, i) => {
                const active = activeBillNo != null && row.bill_no === activeBillNo
                return (
                  <tr
                    key={`${row.bill_no}-${i}`}
                    className={`sa-rowsel${active ? ' sa-rowsel--on' : ''}`}
                    onClick={() => onSelect?.(row)}
                  >
                    <td className="sx-dim">{date(row.date)}</td>
                    <td>{row.bill_no ?? '—'}</td>
                    <td className="sa-wrap">{row.customer ?? '—'}</td>
                    <td className="sx-num">{num(row.qty)}</td>
                    <td className="sx-num">{money(row.mrp)}</td>
                    <td className="sx-num">{row.discount != null ? `${num(row.discount)}%` : '—'}</td>
                  </tr>
                )
              })}
            </tbody>
          </SxTable>
        )}
      </SxCardBody>
    </SxCard>
  )
}

/* ---- Recent Purchases ---------------------------------------------------- */

export function PurchasePanel({ ctx }: { ctx: ProductContext }) {
  const fetcher = useCallback(
    () => stockService.purchaseHistory(ctx.tenantId, ctx.storeId, ctx.productCode),
    [ctx.tenantId, ctx.storeId, ctx.productCode],
  )
  const { data, isLoading, error, reload } = useStockResource(fetcher, panelKey(ctx), 'purchases')

  return (
    <SxCard>
      <SxCardHead title="Recent Purchases" icon="bi-truck" />
      <SxCardBody flush>
        {isLoading ? (
          <div className="p-3"><TableSkeleton rows={4} columns={6} /></div>
        ) : error ? (
          <ErrorState description={error} onRetry={reload} />
        ) : !data || data.length === 0 ? (
          <EmptyState icon="bi-truck" title="No purchases" description="No recent purchases found." />
        ) : (
          <SxTable>
            <colgroup>
              <col /><col style={{ width: '78px' }} />
              <col style={{ width: '46px' }} /><col style={{ width: '46px' }} />
              <col style={{ width: '54px' }} /><col style={{ width: '66px' }} />
              <col style={{ width: '66px' }} /><col style={{ width: '66px' }} />
            </colgroup>
            <thead>
              <tr>
                <th>GRN No.</th><th>Date</th>
                <th className="sx-num">Qty</th><th className="sx-num">Free</th>
                <th className="sx-num">Disc%</th><th className="sx-num">Cost</th>
                <th className="sx-num">PTR</th><th className="sx-num">MRP</th>
              </tr>
            </thead>
            <tbody>
              {data.map((row, i) => (
                <tr key={`${row.grn_no}-${i}`}>
                  <td>{row.grn_no ?? '—'}</td>
                  <td className="sx-dim">{date(row.date)}</td>
                  <td className="sx-num">{num(row.qty)}</td>
                  <td className="sx-num">{num(row.free)}</td>
                  <td className="sx-num">{row.dis != null ? `${num(row.dis)}%` : '—'}</td>
                  <td className="sx-num">{money(row.cost)}</td>
                  <td className="sx-num">{money(row.ptr)}</td>
                  <td className="sx-num">{money(row.mrp)}</td>
                </tr>
              ))}
            </tbody>
          </SxTable>
        )}
      </SxCardBody>
    </SxCard>
  )
}

/* ---- Bill Details -------------------------------------------------------- */

export interface SelectedBill {
  billNo: string
  billDate: string | null
  customer: string | null
}

export function LatestBillPanel({ ctx, selected }: { ctx: ProductContext; selected?: SelectedBill | null }) {
  // Fall back to the most recent sale when no row is selected.
  const salesFetcher = useCallback(
    () => stockService.salesHistory(ctx.tenantId, ctx.storeId, ctx.productCode),
    [ctx.tenantId, ctx.storeId, ctx.productCode],
  )
  const sales = useStockResource(salesFetcher, panelKey(ctx), 'sales')
  const latest = sales.data?.[0] ?? null
  const eff: SelectedBill | null =
    selected ??
    (latest ? { billNo: latest.bill_no ?? '', billDate: latest.date ?? null, customer: latest.customer ?? null } : null)

  const effBillNo = eff?.billNo ?? ''
  const effBillDate = eff?.billDate ?? ''
  const billKey = effBillNo ? `${panelKey(ctx)}|${effBillNo}` : null
  const billFetcher = useCallback(
    () => stockService.billItems(ctx.tenantId, ctx.storeId, effBillNo, effBillDate),
    [ctx.tenantId, ctx.storeId, effBillNo, effBillDate],
  )
  const bill = useStockResource(billFetcher, billKey, 'bill')

  const total = (bill.data ?? []).reduce((sum, row) => sum + (row.amount ?? 0), 0)

  const headerMeta = eff ? (
    <div className="sa-bhdr">
      <span className="sa-bchip"><b>Bill No</b>{eff.billNo || '—'}</span>
      <span className="sa-bchip"><b>Customer</b>{eff.customer || '—'}</span>
      <span className="sa-bchip"><b>Bill Date</b>{date(eff.billDate)}</span>
      <span className="sa-bchip"><b>Amount</b>{money(total)}</span>
    </div>
  ) : undefined

  return (
    <SxCard className="sa-area--bill-card">
      <SxCardHead title="Bill Details" icon="bi-receipt" action={headerMeta} />
      <SxCardBody flush>
        {sales.isLoading || bill.isLoading ? (
          <div className="p-3"><TableSkeleton rows={4} columns={5} /></div>
        ) : sales.error || bill.error ? (
          <ErrorState description={sales.error ?? bill.error ?? 'Failed to load bill'} onRetry={bill.reload} />
        ) : !eff ? (
          <EmptyState icon="bi-receipt" title="No bill" description="Select a sale, or none was found for this product." />
        ) : !bill.data || bill.data.length === 0 ? (
          <EmptyState icon="bi-receipt" title="No bill items" description="This bill has no line items." />
        ) : (
          <>
            <SxTable>
              <colgroup>
                <col style={{ width: '34px' }} /><col /><col style={{ width: '55px' }} />
                <col style={{ width: '50px' }} /><col style={{ width: '70px' }} />
                <col style={{ width: '60px' }} /><col style={{ width: '90px' }} />
              </colgroup>
              <thead>
                <tr>
                  <th>#</th><th>Product</th><th>Unit</th>
                  <th className="sx-num">Qty</th><th className="sx-num">MRP</th>
                  <th className="sx-num">Disc%</th><th className="sx-num">Amount</th>
                </tr>
              </thead>
              <tbody>
                {bill.data.map((row, i) => (
                  <tr key={i}>
                    <td className="sx-dim">{row.line_no ?? i + 1}</td>
                    <td>{row.product_name ?? '—'}</td>
                    <td className="sx-dim">{row.sale_unit ?? '—'}</td>
                    <td className="sx-num">{num(row.qty)}</td>
                    <td className="sx-num">{money(row.mrp)}</td>
                    <td className="sx-num">{row.discount_pct != null ? `${num(row.discount_pct)}%` : '—'}</td>
                    <td className="sx-num">{money(row.amount)}</td>
                  </tr>
                ))}
              </tbody>
            </SxTable>
            <div className="sa-bill-total">
              <span>Total Items: {bill.data.length}</span>
              <SxChip tone="indigo">Total {money(total)}</SxChip>
            </div>
          </>
        )}
      </SxCardBody>
    </SxCard>
  )
}
