import type { CSSProperties } from 'react'
import type { BranchCard as BranchCardData, CrossStoreMatchType, StockProductRow } from '../../types/stock'
import { num, storeColor } from './format'

/** This store's own selection — either the row the user actually clicked
 *  ('SOURCE') or a cross-store equivalent auto-resolved from it. */
export interface BranchSelection {
  productCode: string
  matchType: CrossStoreMatchType | 'SOURCE'
  score: number
}

const MATCH_LABELS: Record<CrossStoreMatchType | 'SOURCE', string> = {
  SOURCE: 'Selected',
  EXACT_SUPPLIER_MATCH: 'Matched via supplier link',
  EXACT_NORMALIZED_NAME: 'Matched via name',
  STRONG_ATTRIBUTE_MATCH: 'Matched via product attributes',
  RELEVANT_FUZZY_MATCH: 'Matched via best-guess relevance',
  NO_MATCH: 'No match',
}

interface BranchCardProps {
  card: BranchCardData
  selection: BranchSelection | null
  onSelect: (card: BranchCardData, product: StockProductRow) => void
}

const MIN_PRODUCT_ROWS = 5

export function BranchCard({ card, selection, onSelect }: BranchCardProps) {
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
          const isActive = selection?.productCode === product.product_code
          const isSource = isActive && selection?.matchType === 'SOURCE'
          const isSync = isActive && !isSource
          const title = isSync && selection
            ? `${MATCH_LABELS[selection.matchType]} (score ${selection.score.toFixed(0)})`
            : undefined
          const stateClass = isSource
            ? ' sa-branch__row--source'
            : isSync
              ? ' sa-branch__row--sync'
              : ''
          return (
            <button
              key={`${product.product_code}-${index}`}
              type="button"
              role="row"
              title={title}
              className={`sa-branch__row${stateClass}`}
              onClick={() => onSelect(card, product)}
            >
              <span className="sa-branch__pname" role="cell">
                <span
                  className={`sa-dot${isSource ? ' sa-dot--selected' : isSync ? ' sa-dot--sync' : ' sa-dot--hidden'}`}
                  aria-hidden="true"
                />
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
