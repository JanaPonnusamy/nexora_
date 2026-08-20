import { settingsService } from '../../platform/services/SettingsService'

// Product Grid columns that live BETWEEN the locked Product (always first)
// and Planning State (always last) columns — spec §5/§6:
//   PRODUCT | user-configurable columns | FINAL QTY | PLANNING STATUS
// finalQty may be reordered within this middle section but can never be
// hidden; stock/suggested stay mandatory too (spec §4's "essential low-res
// columns"). Only pack/unit/offer/remarks are hideable.
export type GridColumnId = 'stock' | 'suggested' | 'pack' | 'unit' | 'offer' | 'finalQty' | 'remarks'

export const MANDATORY_COLUMNS: ReadonlySet<GridColumnId> = new Set(['stock', 'suggested', 'finalQty'])

export const DEFAULT_COLUMN_ORDER: GridColumnId[] = ['pack', 'unit', 'stock', 'suggested', 'finalQty', 'offer', 'remarks']

// Remarks isn't in the default *visible* set from Settings' point of view —
// it only ever renders when the page wires onRemarksChange (Supplier
// Purchasing mode), same as before this config existed. It still needs to be
// "visible" by default for that mode to keep working out of the box, so a
// fresh install shows it exactly where it used to.
export const DEFAULT_VISIBLE_COLUMNS: GridColumnId[] = ['pack', 'unit', 'stock', 'suggested', 'finalQty', 'offer', 'remarks']

// At 1366px/1280x720 the grid must stay usable without horizontal scroll —
// default to the mandatory set only when a user hasn't already saved a
// preference (spec §7's required columns are exactly these plus
// Product/Planning State, which are always rendered regardless).
export const NARROW_DEFAULT_VISIBLE_COLUMNS: GridColumnId[] = ['stock', 'suggested', 'finalQty']

export const COLUMN_LABELS: Record<GridColumnId, string> = {
  pack: 'Pack',
  unit: 'Unit',
  stock: 'Stock',
  suggested: 'Suggested Qty',
  finalQty: 'Final Qty',
  offer: 'Offer',
  remarks: 'Remarks',
}

export interface GridColumnConfig {
  order: GridColumnId[]
  visible: GridColumnId[]
}

const SETTINGS_KEY = 'purchaseWorkspace.columns'

function sanitize(config: GridColumnConfig): GridColumnConfig {
  const known = new Set(DEFAULT_COLUMN_ORDER)
  const order = config.order.filter((id) => known.has(id))
  for (const id of DEFAULT_COLUMN_ORDER) if (!order.includes(id)) order.push(id)
  const visible = config.visible.filter((id) => known.has(id))
  for (const id of MANDATORY_COLUMNS) if (!visible.includes(id)) visible.push(id)
  return { order, visible }
}

export function loadColumnConfig(): GridColumnConfig {
  const saved = settingsService.get<GridColumnConfig | null>(SETTINGS_KEY, null)
  if (!saved) return { order: [...DEFAULT_COLUMN_ORDER], visible: [...DEFAULT_VISIBLE_COLUMNS] }
  return sanitize(saved)
}

/** True once the user has explicitly changed their column preference — lets
 *  callers tell "still on the factory default" apart from "chose this on
 *  purpose", e.g. to only apply the narrow-width default column set (spec
 *  §7) before any deliberate choice exists. */
export function hasSavedColumnConfig(): boolean {
  return settingsService.get<GridColumnConfig | null>(SETTINGS_KEY, null) !== null
}

export function saveColumnConfig(config: GridColumnConfig): void {
  settingsService.set(SETTINGS_KEY, sanitize(config))
}
