import type { ReactNode } from 'react'
import { DockGroup, DockPanelItem, DockSeparator } from '../../platform/workspace/DockPanel'
import { useNarrowWorkspace } from '../../hooks/useNarrowWorkspace'

/**
 * The Purchase Workspace's three-column split — Product Grid | Supplier
 * Recommendation | Product Detail, as three independent siblings in that
 * fixed order (spec §1/§2). Each is its own DockPanelItem with its own full
 * height and its own internal scrolling — Supplier Recommendation and
 * Product Detail are NOT stacked into a shared column. Defaults are ~50/23/27
 * (Product Grid stays the largest, primary working area, but Supplier
 * Recommendation and especially Product Detail get enough width to be
 * genuinely usable — Purchase/Sales History need to show every column
 * without horizontal scrolling — rather than a narrow sidebar; spec §3-§7).
 *
 * Percentage-only, deliberately, and as explicit "%"-suffixed STRINGS: a
 * bare number for minSize/maxSize is pixels per the library's own unit rule
 * (only defaultSize behaves as a proportional share when given a bare
 * number) — passing a bare number here silently clamped the panel to a
 * literal 24px (reproduced). A pixel min/max mixed with the siblings'
 * percentage defaults also separately mis-computed a panel's share
 * (reproduced), and a CSS min-width/max-width override on a panel's content
 * div made the library's own position bookkeeping diverge from the rendered
 * box, visually overlapping panels (also reproduced). All three were tried;
 * explicit "%" strings on minSize/maxSize is the only configuration that has
 * actually rendered correctly.
 * Widths are drag-resizable via DockGroup, which also persists the chosen
 * sizes to localStorage (spec §3/§6 "persist the user's configuration") — a
 * user who has already dragged a separator keeps their own saved sizes;
 * this default only applies on first load.
 *
 * At <=1366px (spec §7 — 1280x720 / 1366x768) the Supplier Recommendation
 * column is dropped from the permanent layout and instead rendered as a
 * floating card, shown only while `supplierActive` is true (spec §8) — the
 * existing ProductGrid keyboard zone (Right Arrow opens it, Esc/Left Arrow
 * close it) already drives that flag; no new keyboard logic is added here.
 */
export function PmWorkspaceSplit({
  id,
  stockVariant = false,
  grid,
  suppliers,
  detail,
  supplierActive,
}: {
  /** Unique id for this split's persisted layout (e.g. "review", "stock"). */
  id: string
  /** Slightly different default proportions for the Supplier Live Stock grid
   *  (spec-driven §2 note: that grid needs more of the row). */
  stockVariant?: boolean
  grid: ReactNode
  suppliers: ReactNode
  detail: ReactNode
  /** True while the keyboard Supplier Recommendation zone is active — opens
   *  the floating card at narrow widths. */
  supplierActive: boolean
}) {
  const narrow = useNarrowWorkspace()

  if (narrow) {
    return (
      <div className="pm-workspace-narrow">
        <DockGroup id={`purchaseWorkspace.${id}.narrow`}>
          <DockPanelItem id="grid" defaultSize={62} minSize="40%" className="pm-split__grid">
            {grid}
          </DockPanelItem>
          <DockSeparator />
          <DockPanelItem id="detail" defaultSize={38} minSize="22%" className="pm-split__detail">
            {detail}
          </DockPanelItem>
        </DockGroup>
        {supplierActive && (
          <div className="pm-srp-overlay" role="dialog" aria-label="Supplier Recommendation">
            <div className="pm-split__suppliers pm-split__suppliers--floating">{suppliers}</div>
          </div>
        )}
      </div>
    )
  }

  return (
    // ".3col-v2" suffix: the proportions changed again (57/21/22 -> 50/23/27,
    // Product Detail needed real room for the history tables). Same rationale
    // as the earlier ".3col" bump — defaultSize only applies when NO layout is
    // saved under this exact key, so a user with an old saved layout would
    // otherwise keep the cramped Product Detail column forever. Bumping the
    // key is the established fix (see the previous ".3col" migration note in
    // git history) rather than requiring anyone to clear localStorage by hand.
    <DockGroup id={`purchaseWorkspace.${id}.3col-v2`}>
      <DockPanelItem
        id="grid"
        defaultSize={50}
        minSize="42%"
        maxSize="56%"
        className={stockVariant ? 'pm-split__grid pm-stockgrid' : 'pm-split__grid'}
      >
        {grid}
      </DockPanelItem>
      <DockSeparator />
      <DockPanelItem
        id="suppliers"
        defaultSize={23}
        minSize="19%"
        maxSize="27%"
        className="pm-split__suppliers"
      >
        {suppliers}
      </DockPanelItem>
      <DockSeparator />
      <DockPanelItem
        id="detail"
        defaultSize={27}
        minSize="24%"
        maxSize="34%"
        className="pm-split__detail"
      >
        {detail}
      </DockPanelItem>
    </DockGroup>
  )
}
