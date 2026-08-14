import type { CSSProperties } from 'react'
import type { BranchCard as BranchCardData, StockProductRow } from '../../types/stock'
import { num, storeColor } from './format'

interface BranchCardProps {
  card: BranchCardData
  activeProductCode: string | null
  activeStoreId: string | null
  onSelect: (card: BranchCardData, product: StockProductRow) => void
}

const MIN_PRODUCT_ROWS = 5

export function BranchCard({ card, activeProductCode, activeStoreId, onSelect }: BranchCardProps) {
  const label = card.store_code ?? card.store_name ?? 'Store'
  const color = storeColor(card.store_code ?? card.store_id)
  const fillerRows = Math.max(0, MIN_PRODUCT_ROWS - card.products.length)

  return (
    <div className="sa-branch" style={{ '--sa-store': color.accent, '--sa-store-soft': color.soft } as CSSProperties}>
      <div className="sa-branch__head">
        <span className="sa-branch__name">{label}</span>
        <span className="sa-branch__code">{card.store_name ?? ''}</span>
      </div>

      <div className="sa-branch__grid" role="table" aria-label={`Products in ${label}`}>
        <div className="sa-branch__row sa-branch__row--head" role="row">
          <span role="columnheader">Product Name</span>
          <span role="columnheader">Unit</span>
          <span className="sa-num" role="columnheader">Stock</span>
        </div>
        {card.products.map((product, index) => {
          const isActive =
            activeStoreId === card.store_id && activeProductCode === product.product_code
          return (
            <button
              key={`${product.product_code}-${index}`}
              type="button"
              role="row"
              className={`sa-branch__row${isActive ? ' sa-branch__row--active' : ''}`}
              onClick={() => onSelect(card, product)}
            >
              <span className="sa-branch__pname" role="cell">
                <span className={`sa-dot${isActive ? ' sa-dot--selected' : ' sa-dot--hidden'}`} aria-hidden="true" />
                {product.product_name ?? '—'}
              </span>
              <span className="sa-dim" role="cell">{product.sale_unit ?? '—'}</span>
              <span className="sa-num" role="cell">{num(product.stock)}</span>
            </button>
          )
        })}
        {Array.from({ length: fillerRows }).map((_, index) => (
          <div key={`filler-${index}`} className="sa-branch__row sa-branch__row--empty" role="row" aria-hidden="true">
            <span className="sa-branch__pname">&nbsp;</span>
            <span className="sa-dim" />
            <span className="sa-num" />
          </div>
        ))}
      </div>
    </div>
  )
}
