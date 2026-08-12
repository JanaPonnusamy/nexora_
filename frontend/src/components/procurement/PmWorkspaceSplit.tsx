import type { ReactNode } from 'react'
import { DockGroup, DockPanelItem, DockSeparator } from '../../platform/workspace/DockPanel'
import { useNarrowWorkspace } from '../../hooks/useNarrowWorkspace'

/**
 * The Purchase Workspace's master/detail split — Product Grid | Supplier
 * Recommendation (with Product Details stacked underneath, same column), in
 * that fixed order (spec §2). Widths default to ~72/28 (owner-directed:
 * Supplier Recommendation + Details share one narrower right column instead
 * of each being its own full-height panel — Product Grid keeps the space
 * that frees up). The combined column's DockPanelItem carries a percentage
 * minSize/maxSize (22–32%) so it can't uncontrollably flex-grow wide on
 * large monitors.
 *
 * Percentage-only, deliberately, and as explicit "%"-suffixed STRINGS: a
 * bare number for minSize/maxSize is pixels per the library's own unit rule
 * (only defaultSize behaves as a proportional share when given a bare
 * number) — passing a bare number here silently clamped the panel to a
 * literal 24px (reproduced). A pixel min/max mixed with the siblings'
 * percentage defaults also separately mis-computed the third panel's share
 * (reproduced), and a CSS min-width/max-width override on
 * .pm-split__suppliers made the library's own position bookkeeping diverge
 * from the rendered box, visually overlapping the suppliers/detail panels
 * (also reproduced). All three were tried; explicit "%" strings on
 * minSize/maxSize is the only configuration that has actually rendered
 * correctly.
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
    <DockGroup id={`purchaseWorkspace.${id}`}>
      <DockPanelItem
        id="grid"
        defaultSize={72}
        minSize="45%"
        className={stockVariant ? 'pm-split__grid pm-stockgrid' : 'pm-split__grid'}
      >
        {grid}
      </DockPanelItem>
      <DockSeparator />
      <DockPanelItem
        id="side"
        defaultSize={28}
        minSize="22%"
        maxSize="32%"
        className="pm-split__side"
      >
        <div className="pm-split__suppliers">{suppliers}</div>
        <div className="pm-split__detail">{detail}</div>
      </DockPanelItem>
    </DockGroup>
  )
}
