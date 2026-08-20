import type { PiRow, PiStoreColumn } from '../../../types/intelligence'
import { num } from '../../stock/format'

/**
 * The network procurement grid. One row = ONE CANONICAL SUPPLIER PRODUCT (the
 * same real product, however differently each store codes it) — never one store's
 * product. Stores are merged on the Common Product Mapping, never on ProductCode.
 *
 * Every quantity is network-wide: Need is the sum of EVERY store's own suggested
 * qty, Purchase is what the WAREHOUSE must buy to serve the whole network.
 *
 * The table is fixed-layout: the store columns divide whatever width is left
 * between however many stores exist, so the grid always fits the viewport and
 * NEVER scrolls sideways. Big metrics live in the right panel, not in a cell.
 */

const PRIORITY_CLASS: Record<string, string> = {
  CRITICAL: 'pi-pri--critical',
  HIGH: 'pi-pri--high',
  MEDIUM: 'pi-pri--medium',
  NONE: 'pi-pri--none',
}

export function IntelligenceGrid({
  rows,
  stores,
  selectedId,
  onSelect,
}: {
  rows: PiRow[]
  stores: PiStoreColumn[]
  selectedId: string | null
  onSelect: (row: PiRow) => void
}) {
  return (
    <table className="pi-grid">
      <colgroup>
        <col className="pi-c-prod" />
        <col className="pi-c-xs" />
        <col className="pi-c-sm" />
        <col className="pi-c-sm" />
        <col className="pi-c-sm" />
        <col className="pi-c-pri" />
        <col className="pi-c-xs" />
        {stores.map((s) => <col key={s.store_id} className="pi-c-store" />)}
      </colgroup>
      <thead>
        <tr>
          <th>Supplier Product</th>
          <th className="pi-num" title="Stores this product is mapped into">Stores</th>
          <th className="pi-num pi-th-need" title="Network demand — every store's own suggested qty">Need</th>
          <th className="pi-num pi-th-buy" title="What the warehouse must BUY for the network">Purchase</th>
          <th className="pi-num" title="Servable from warehouse stock instead of buying">Transfer</th>
          <th title="CRITICAL = a store is selling this and has run out">Priority</th>
          <th className="pi-num" title="Weakest mapping edge behind this row">Conf</th>
          {stores.map((s) => (
            <th key={s.store_id} className="pi-num pi-th-store" title={s.store_name ?? undefined}>
              {s.store_code ?? '—'}
              {s.is_warehouse && <i className="bi bi-house-fill" />}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => {
          const isTransfer = r.consolidated_purchase_qty === 0 && r.transfer_qty > 0
          return (
            <tr
              key={r.cache_id}
              data-cache={r.cache_id}
              className={selectedId === r.cache_id ? 'pi-row--sel' : undefined}
              onClick={() => onSelect(r)}
            >
              <td className="pi-cell-prod" title={r.product_name ?? r.supplier_product_name ?? undefined}>
                {r.product_name ?? r.supplier_product_name ?? '—'}
                {!r.warehouse_product_code && (
                  <span className="pi-tag pi-tag--nowh" title="The warehouse does not stock it — the network needs it anyway">
                    NO WH
                  </span>
                )}
              </td>
              <td className="pi-num">{r.mapped_store_count}</td>
              <td className="pi-num pi-need">{num(r.consolidated_suggest_qty)}</td>
              <td className={`pi-num pi-buy${isTransfer ? ' pi-buy--zero' : ''}`}>
                {num(r.consolidated_purchase_qty)}
              </td>
              <td className="pi-num pi-xfer">{num(r.transfer_qty)}</td>
              <td>
                <span className={`pi-pri ${PRIORITY_CLASS[r.priority ?? 'NONE'] ?? 'pi-pri--none'}`}>
                  {r.priority ?? '—'}
                </span>
              </td>
              <td className="pi-num" title={r.match_method ?? undefined}>
                {r.confidence != null ? num(r.confidence) : '—'}
              </td>
              {stores.map((s) => {
                const cell = r.stores[s.store_id]
                if (!cell) return <td key={s.store_id} className="pi-num pi-cell--blank">·</td>
                const sug = cell.suggested_qty ?? 0
                const stock = cell.stock_qty ?? 0
                return (
                  <td
                    key={s.store_id}
                    className="pi-num pi-cell-store"
                    title={`${s.store_code ?? ''} · needs ${num(sug)} · stock ${num(stock)}`}
                  >
                    <b className={sug === 0 ? 'pi-zero' : undefined}>{num(sug)}</b>
                    <i className={stock <= 0 ? 'pi-out' : undefined}>{num(stock)}</i>
                  </td>
                )
              })}
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
