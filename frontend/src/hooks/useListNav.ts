import { useEffect, useRef, useState } from 'react'

/**
 * Shared keyboard-navigation index for search/autocomplete result lists
 * (Supplier Search, Product Search, ...). Tracks the highlighted row, clamps
 * it when the result count shrinks, and keeps the highlighted element
 * scrolled into view — the mechanics every "type → results → arrow keys →
 * Enter" dropdown in this app needs. Each caller still renders its own
 * list/table markup and owns its own onKeyDown/onPick — this only owns the
 * index + scroll behavior, so the different result layouts (Supplier
 * Picker's `<ul>`, the manual-product modal's `<table>`) don't have to share
 * a component, only this mechanic.
 */
export function useListNav(length: number) {
  const [active, setActive] = useState(0)
  const itemRefs = useRef<Map<number, HTMLElement>>(new Map())

  // Keep the index in range as the result set shrinks (e.g. a narrower search).
  useEffect(() => {
    setActive((a) => (length === 0 ? 0 : Math.min(a, length - 1)))
  }, [length])

  useEffect(() => {
    itemRefs.current.get(active)?.scrollIntoView({ block: 'nearest' })
  }, [active])

  const moveNext = () => setActive((a) => Math.min(a + 1, Math.max(0, length - 1)))
  const movePrev = () => setActive((a) => Math.max(a - 1, 0))
  const reset = () => setActive(0)
  const itemRef = (i: number) => (el: HTMLElement | null) => {
    if (el) itemRefs.current.set(i, el)
    else itemRefs.current.delete(i)
  }

  return { active, setActive, moveNext, movePrev, reset, itemRef }
}
