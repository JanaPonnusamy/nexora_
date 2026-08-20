import { useCallback, useEffect, useRef, useState } from 'react'
import { gridSettingsService, type GridSettingsPayload } from '../../services/gridSettingsService'
import { settingsService } from '../../platform/services/SettingsService'

export interface MiniGridColumn {
  id: string
  label: string
  width: number
}

const SAVE_DEBOUNCE_MS = 600

/** Column order/width/padding for one grid — live-preview locally, persisted
 *  to the backend per-user (dbo.user_grid_settings, keyed by gridKey) so it
 *  follows the user across devices, with an instant localStorage mirror so
 *  the grid doesn't flash defaults while the network round-trip is in
 *  flight. */
export function useMiniGridSettings(gridKey: string, columns: MiniGridColumn[], defaultPadding: number) {
  const defaultOrder = columns.map((c) => c.id)
  const defaultWidths = Object.fromEntries(columns.map((c) => [c.id, c.width ?? 50])) as Record<string, number>

  const cacheKey = `gridSettings.${gridKey}`
  const cached = settingsService.get<GridSettingsPayload | null>(cacheKey, null)

  const [order, setOrder] = useState<string[]>(cached?.columnOrder ?? defaultOrder)
  const [widths, setWidths] = useState<Record<string, number>>(cached?.columnWidths ?? defaultWidths)
  const [padding, setPaddingState] = useState<number>(cached?.padding ?? defaultPadding)
  const [loaded, setLoaded] = useState(false)

  const saveTimer = useRef<number | undefined>(undefined)

  useEffect(() => {
    let cancelled = false
    gridSettingsService.get(gridKey).then((res) => {
      if (cancelled || !res.settings) return
      const ids = new Set(defaultOrder)
      const savedOrder = res.settings.columnOrder.filter((id) => ids.has(id))
      const missing = defaultOrder.filter((id) => !savedOrder.includes(id))
      setOrder([...savedOrder, ...missing])
      setWidths({ ...defaultWidths, ...res.settings.columnWidths })
      setPaddingState(res.settings.padding ?? defaultPadding)
    }).catch(() => { /* keep local/cached state */ }).finally(() => { if (!cancelled) setLoaded(true) })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gridKey])

  const persist = useCallback((next: GridSettingsPayload) => {
    settingsService.set(cacheKey, next)
    window.clearTimeout(saveTimer.current)
    saveTimer.current = window.setTimeout(() => {
      gridSettingsService.save(gridKey, next).catch(() => { /* best-effort */ })
    }, SAVE_DEBOUNCE_MS)
  }, [cacheKey, gridKey])

  const moveColumn = useCallback((id: string, dir: -1 | 1) => {
    setOrder((prev) => {
      const i = prev.indexOf(id)
      const j = i + dir
      if (i < 0 || j < 0 || j >= prev.length) return prev
      const next = [...prev]
      ;[next[i], next[j]] = [next[j], next[i]]
      persist({ columnOrder: next, columnWidths: widths, padding })
      return next
    })
  }, [persist, widths, padding])

  const setColumnWidth = useCallback((id: string, px: number) => {
    setWidths((prev) => {
      const next = { ...prev, [id]: Math.max(24, Math.round(px)) }
      persist({ columnOrder: order, columnWidths: next, padding })
      return next
    })
  }, [persist, order, padding])

  const setPadding = useCallback((px: number) => {
    const next = Math.max(0, Math.round(px))
    setPaddingState(next)
    persist({ columnOrder: order, columnWidths: widths, padding: next })
  }, [persist, order, widths])

  const reset = useCallback(() => {
    setOrder(defaultOrder)
    setWidths(defaultWidths)
    setPaddingState(defaultPadding)
    settingsService.remove(cacheKey)
    gridSettingsService.reset(gridKey).catch(() => { /* best-effort */ })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gridKey, cacheKey])

  return { order, widths, padding, loaded, moveColumn, setColumnWidth, setPadding, reset }
}
