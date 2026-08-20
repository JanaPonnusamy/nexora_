import { useMediaQuery } from './useMediaQuery'

// 1366px covers both 1280x720 and 1366x768 — the two resolutions the Purchase
// Workspace must explicitly support (spec §7/§22). Below this width the
// permanent 3-panel split loses the Supplier Recommendation column; it
// reappears as a floating card on demand (§8).
const NARROW_QUERY = '(max-width: 1366px)'

/** True at 1366px and below (1280x720 / 1366x768) — drives the Purchase
 *  Workspace's 2-panel responsive mode. */
export function useNarrowWorkspace(): boolean {
  return useMediaQuery(NARROW_QUERY)
}
