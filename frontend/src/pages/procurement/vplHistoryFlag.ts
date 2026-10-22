/** Local/dev switch for the VPL history screen. Defaults off.

PROCUREMENT_ADMIN is still required on the route. This flag does not
replace that check. Set `VITE_VPL_HISTORY_SCREEN=1` or
`localStorage['nexora.vplHistoryScreen']='1'` to open the screen.
The screen never calls live generation or clear_products.
*/
export const VPL_HISTORY_SCREEN_STORAGE_KEY = 'nexora.vplHistoryScreen'

export function isVplHistoryScreenEnabled(): boolean {
  if (import.meta.env.VITE_VPL_HISTORY_SCREEN === '1') return true
  try {
    return globalThis.localStorage?.getItem(VPL_HISTORY_SCREEN_STORAGE_KEY) === '1'
  } catch {
    return false
  }
}
