import type { PiOfferRow, PiStoreColumn } from '../../../types/intelligence'
import { money, num } from '../../stock/format'

/**
 * Mode 2 — Supplier Offer Intelligence. Every line the supplier is offering, read
 * against the NETWORK:
 *
 *     supplier line -> SupplierProductMatch -> warehouse product
 *                   -> the canonical product -> network need / other stores
 *
 * A line that has never been matched is NOT hidden. It shows an Assign button in
 * its own row, and the buyer maps it here — Product Intelligence is not left.
 */

const PRIORITY_CLASS: Record<string, string> = {
  CRITICAL: 'pi-pri--critical',
  HIGH: 'pi-pri--high',
  MEDIUM: 'pi-pri--medium',
  NONE: 'pi-pri--none',
}

export function SupplierOfferGrid({
  rows,
  stores,
  selectedKey,
  onSelect,
  onAssign,
}: {
  rows: PiOfferRow[]
  stores: PiStoreColumn[]
  selectedKey: string | null
  onSelect: (row: PiOfferRow) => void
  onAssign: (row: PiOfferRow) => void
}) {
  return (
    <table className="pi-grid">
      <colgroup>
        <col className="pi-c-prod" />
        <col className="pi-c-sm" />
        <col className="pi-c-sm" />
        <col className="pi-c-xs" />
        <col className="pi-c-sm" />
        <col className="pi-c-sm" />
        <col className="pi-c-sm" />
        <col className="pi-c-pri" />
        {stores.map((s) => <col key={s.store_id} className="pi-c-store" />)}
      </colgroup>
      <thead>
        <tr>
          <th>Supplier Product</th>
          <th className="pi-num" title="Stock the supplier is offering">Offer</th>
          <th className="pi-num">PTR</th>
          <th className="pi-num" title="Discount %">Dis</th>
          <th className="pi-num pi-th-need" title="Network demand across every store">Need</th>
          <th className="pi-num pi-th-buy" title="What the warehouse must buy for the network">Purchase</th>
          <th className="pi-num">Transfer</th>
          <th>Priority</th>
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
          const key = `${r.supplier_product_code ?? r.supplier_product_name}`
          return (
            <tr
              key={key}
              data-cache={key}
              className={`${selectedKey === key ? 'pi-row--sel ' : ''}${!r.mapped ? 'pi-row--unmapped' : ''}`}
              onClick={() => onSelect(r)}
            >
              <td className="pi-cell-prod" title={r.supplier_product_name ?? undefined}>
                {r.supplier_product_name ?? r.supplier_product_code ?? '—'}
                {r.mapped ? (
                  !r.in_network && (
                    <span className="pi-tag pi-tag--noneed" title="Mapped, but no store needs it right now">
                      NO NEED
                    </span>
                  )
                ) : (
                  <button
                    type="button"
                    className="pi-assign"
                    onClick={(e) => { e.stopPropagation(); onAssign(r) }}
                  >
                    <i className="bi bi-link-45deg" /> Assign
                  </button>
                )}
              </td>
              <td className="pi-num">{num(r.available_stock)}</td>
              <td className="pi-num">{money(r.ptr)}</td>
              <td className="pi-num">{r.discount != null ? num(r.discount) : '—'}</td>
              <td className="pi-num pi-need">{r.mapped ? num(r.consolidated_suggest_qty) : '—'}</td>
              <td className="pi-num pi-buy">{r.mapped ? num(r.consolidated_purchase_qty) : '—'}</td>
              <td className="pi-num pi-xfer">{r.mapped ? num(r.transfer_qty) : '—'}</td>
              <td>
                {r.mapped ? (
                  <span className={`pi-pri ${PRIORITY_CLASS[r.priority ?? 'NONE'] ?? 'pi-pri--none'}`}>
                    {r.priority ?? '—'}
                  </span>
                ) : (
                  <span className="pi-pri pi-pri--unmapped">UNMAPPED</span>
                )}
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
