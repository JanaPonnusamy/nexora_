import { useCallback, useRef } from 'react'

/** Keeps every store column's cell in one band scrolled to the same offset,
 * so a row at a given vertical position means the same thing (the same
 * product, the same purchase/sale date) in every column — without this,
 * each cell's own independent scrollbar lets columns drift out of sync as
 * soon as any one of them is scrolled.
 *
 * `refFor(key)` returns a stable ref callback for a given store id; attach
 * it to that store's cell `div` in this band. Scrolling any one of them
 * mirrors scrollTop onto every other registered cell in the same band. */
export function useScrollSync() {
  const elsRef = useRef<Map<string, HTMLDivElement>>(new Map())
  const cleanupRef = useRef<Map<string, () => void>>(new Map())
  const syncingRef = useRef(false)
  const refCallbacksRef = useRef<Map<string, (el: HTMLDivElement | null) => void>>(new Map())

  const syncFrom = useCallback((source: HTMLDivElement) => {
    if (syncingRef.current) return
    syncingRef.current = true
    elsRef.current.forEach((el) => {
      if (el !== source && el.scrollTop !== source.scrollTop) el.scrollTop = source.scrollTop
    })
    syncingRef.current = false
  }, [])

  const refFor = useCallback((key: string) => {
    let cb = refCallbacksRef.current.get(key)
    if (cb) return cb
    cb = (el: HTMLDivElement | null) => {
      const prevCleanup = cleanupRef.current.get(key)
      if (prevCleanup) {
        prevCleanup()
        cleanupRef.current.delete(key)
      }
      elsRef.current.delete(key)
      if (!el) return
      const onScroll = () => syncFrom(el)
      el.addEventListener('scroll', onScroll, { passive: true })
      elsRef.current.set(key, el)
      cleanupRef.current.set(key, () => el.removeEventListener('scroll', onScroll))
    }
    refCallbacksRef.current.set(key, cb)
    return cb
  }, [syncFrom])

  return refFor
}
