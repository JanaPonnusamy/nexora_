import { useSyncExternalStore } from 'react'

function subscribe(query: string) {
  return (callback: () => void): (() => void) => {
    if (typeof window === 'undefined' || !window.matchMedia) return () => {}
    const mql = window.matchMedia(query)
    mql.addEventListener('change', callback)
    return () => mql.removeEventListener('change', callback)
  }
}

function getSnapshot(query: string) {
  return (): boolean => {
    if (typeof window === 'undefined' || !window.matchMedia) return false
    return window.matchMedia(query).matches
  }
}

/** Generic reactive matchMedia hook — reevaluates on real viewport/window
 *  resize (not on Electron CDP device-metrics emulation, which doesn't fire
 *  a native resize event; a real OS window resize always does). */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(subscribe(query), getSnapshot(query), () => false)
}
