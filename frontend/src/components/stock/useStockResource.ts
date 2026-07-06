import { useCallback, useEffect, useState } from 'react'

/**
 * Lazy, key-driven read hook for the detail panels. Re-fetches whenever `key`
 * changes (e.g. the active product context) and skips fetching entirely while
 * `key` is null — so panels stay idle until a product is selected.
 */
export function useStockResource<T>(fetcher: () => Promise<T>, key: string | null) {
  const [data, setData] = useState<T | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!key) {
      setData(null)
      setError(null)
      setIsLoading(false)
      return
    }
    setIsLoading(true)
    setError(null)
    try {
      setData(await fetcher())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data')
    } finally {
      setIsLoading(false)
    }
    // fetcher is rebuilt by the caller for each key; key is the real dependency
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  useEffect(() => {
    void load()
  }, [load])

  return { data, isLoading, error, reload: load }
}
