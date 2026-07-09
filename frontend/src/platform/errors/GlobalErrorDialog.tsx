import { useEffect, useState } from 'react'
import { errorService, type PlatformError } from './ErrorService'

const AUTO_DISMISS_MS = 8000

/**
 * One shared error surface for the whole shell — modules report failures via
 * errorService.report() instead of rolling their own top-level dialog.
 * Inline, field-level error UI stays a module concern; this is only for
 * unhandled/unexpected failures.
 */
export function GlobalErrorDialog() {
  const [errors, setErrors] = useState<PlatformError[]>([])

  useEffect(() => {
    return errorService.subscribe((error) => {
      setErrors((prev) => [...prev, error])
      setTimeout(() => {
        setErrors((prev) => prev.filter((e) => e.id !== error.id))
      }, AUTO_DISMISS_MS)
    })
  }, [])

  if (errors.length === 0) return null

  return (
    <div className="platform-error-stack" role="alert" aria-live="assertive">
      {errors.map((error) => (
        <div key={error.id} className="platform-error-toast">
          <i className="bi bi-exclamation-triangle-fill" aria-hidden="true" />
          <div className="platform-error-toast__body">
            <div className="platform-error-toast__scope">{error.scope}</div>
            <div className="platform-error-toast__message">{error.message}</div>
          </div>
          <button
            type="button"
            className="btn-close"
            aria-label="Dismiss"
            onClick={() => setErrors((prev) => prev.filter((e) => e.id !== error.id))}
          />
        </div>
      ))}
    </div>
  )
}
