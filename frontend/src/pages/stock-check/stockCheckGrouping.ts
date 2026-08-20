import type { StockCheckRow } from '../../types/stockCheckReport'

/** A product is marked non-moving ("NM") when every one of its batches was
 *  last sold more than this many days ago (or never sold). */
export const NON_MOVING_DAYS = 120

export interface ProductGroup {
  productCode: string
  sublocation: string
  rows: StockCheckRow[]
  nonMoving: boolean
}

export interface SublocationGroup {
  sublocation: string
  products: ProductGroup[]
}

export function isExpired(dateStr: string | null, today: Date = new Date()): boolean {
  if (!dateStr) return false
  return new Date(dateStr).getTime() < today.getTime()
}

/** Groups flat batch rows into sublocation -> product -> batches, mirroring the
 *  legacy Excel layout: rows already come sorted by sublocation, product name,
 *  expiry, so consecutive rows sharing a product code are one product's
 *  batches (merged in the sheet), and a sublocation change starts a new
 *  visual block (blank separator row in the sheet). */
export function groupStockCheckRows(rows: StockCheckRow[]): SublocationGroup[] {
  const groups: SublocationGroup[] = []
  let currentSub: SublocationGroup | null = null
  let currentProduct: ProductGroup | null = null

  for (const row of rows) {
    const sub = row.sublocation ?? ''
    if (!currentSub || currentSub.sublocation !== sub) {
      currentSub = { sublocation: sub, products: [] }
      groups.push(currentSub)
      currentProduct = null
    }
    const productCode = row.product_code ?? ''
    if (!currentProduct || currentProduct.productCode !== productCode) {
      currentProduct = { productCode, sublocation: sub, rows: [], nonMoving: false }
      currentSub.products.push(currentProduct)
    }
    currentProduct.rows.push(row)
  }

  for (const sub of groups) {
    for (const product of sub.products) {
      // purchase_days/sale_days are product-level (identical across every
      // batch row of the product), so the first row's value is authoritative.
      product.nonMoving = (product.rows[0]?.sale_days ?? Infinity) > NON_MOVING_DAYS
    }
  }

  return groups
}
