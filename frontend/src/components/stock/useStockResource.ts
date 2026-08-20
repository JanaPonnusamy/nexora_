import { useCallback, useEffect, useRef, useState } from 'react'

// Shared LRU cache across every useStockResource instance (Purchase Manager
// Decision Panel + Stock Availability panels both use this hook). Namespaced
// by the caller-supplied `resource` name so two different resource types can
// never collide on the same product context key (e.g. the Decision Panel's
// sales / purchases / movement calls all share one product context key).
const CACHE_LIMIT = 80
const cache = new Map<string, unknown>()

function cacheGet<T>(cacheKey: string): T | undefined {
  if (!cache.has(cacheKey)) return undefined
  const hit = cache.get(cacheKey) as T
  // Map preserves insertion order — re-insert to mark this entry most-recently-used.
  cache.delete(cacheKey)
  cache.set(cacheKey, hit)
  return hit
}

function cacheSet<T>(cacheKey: string, value: T) {
  cache.delete(cacheKey)
  cache.set(cacheKey, value)
  if (cache.size > CACHE_LIMIT) {
    const oldest = cache.keys().next().value
    if (oldest !== undefined) cache.delete(oldest)
  }
}

// Rapid key changes (arrow-key navigation through many grid rows) must not
// fire one request per intermediate row — only the row the user settles on.
const DEBOUNCE_MS = 180

/**
 * Lazy, key-driven read hook for the detail panels. Re-fetches whenever `key`
 * changes (e.g. the active product context) and skips fetching entirely while
 * `key` is null — so panels stay idle until a product is selected.
 *
 * `resource` namespaces the shared cache (e.g. 'sales', 'purchases',
 * 'movement') — required so callers that share one context key across
 * several resource types don't clobber each other's cached data. A cache hit
 * renders instantly (no debounce, no loading flicker); a miss is debounced.
 */
export function useStockResource<T>(fetcher: () => Promise<T>, key: string | null, resource: string) {
  const cacheKey = key ? `${resource}:${key}` : null
  const [data, setData] = useState<T | null>(() => (cacheKey ? cacheGet<T>(cacheKey) ?? null : null))
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Guards a slow response (superseded by a newer key before it resolved)
  // from overwriting fresher state.
  const activeKeyRef = useRef<string | null>(null)

  const load = useCallback(
    async (bypassCache = false) => {
      if (!cacheKey) {
        setData(null)
        setError(null)
        setIsLoading(false)
        return
      }
      if (!bypassCache) {
        const cached = cacheGet<T>(cacheKey)
        if (cached !== undefined) {
          setData(cached)
          setError(null)
          setIsLoading(false)
          return
        }
      }
      activeKeyRef.current = cacheKey
      setIsLoading(true)
      setError(null)
      try {
        const result = await fetcher()
        if (activeKeyRef.current !== cacheKey) return // superseded
        cacheSet(cacheKey, result)
        setData(result)
      } catch (err) {
        if (activeKeyRef.current !== cacheKey) return
        setError(err instanceof Error ? err.message : 'Failed to load data')
      } finally {
        if (activeKeyRef.current === cacheKey) setIsLoading(false)
      }
    },
    [cacheKey, fetcher],
  )

  useEffect(() => {
    if (!cacheKey) {
      void load()
      return
    }
    const cached = cacheGet<T>(cacheKey)
    if (cached !== undefined) {
      setData(cached)
      setError(null)
      setIsLoading(false)
      return
    }
    const t = window.setTimeout(() => void load(), DEBOUNCE_MS)
    return () => window.clearTimeout(t)
  }, [cacheKey, load])

  // Retry / explicit refresh bypasses the cache so it can pick up new data.
  const reload = useCallback(() => load(true), [load])

  return { data, isLoading, error, reload }
}
