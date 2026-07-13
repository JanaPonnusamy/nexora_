import { useEffect, useState } from 'react'
import { api } from '../services/apiClient'

/**
 * Fetches a backend image path (original/preview page images — auth-gated,
 * like every other API call) as a Blob and exposes it as an object URL a
 * plain <img src> can use. A bare <img src="/api/...">  would skip the
 * Authorization header apiClient adds, so every image display in this
 * module goes through this hook instead. Revokes the object URL on
 * unmount/path change to avoid leaking blob URLs.
 */
export function useAuthorizedImage(path: string | null | undefined): { url: string | null; error: boolean } {
  const [url, setUrl] = useState<string | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    if (!path) {
      setUrl(null)
      setError(false)
      return
    }
    let objectUrl: string | null = null
    let cancelled = false
    setError(false)
    api.blob(path)
      .then((blob) => {
        if (cancelled) return
        objectUrl = URL.createObjectURL(blob)
        setUrl(objectUrl)
      })
      .catch(() => {
        if (!cancelled) setError(true)
      })
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [path])

  return { url, error }
}
