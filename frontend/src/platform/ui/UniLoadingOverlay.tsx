interface UniLoadingOverlayProps {
  label?: string
  /** Covers the nearest positioned ancestor's full box instead of just centering inline. */
  fullPage?: boolean
}

/**
 * Shared loading overlay — layers a spinner over in-flight content instead
 * of every module rolling its own. Distinct from Skeleton (content-shaped
 * placeholders shown before any data exists): this is for re-fetches over
 * content that's already rendered once.
 */
export function UniLoadingOverlay({ label = 'Loading…', fullPage }: UniLoadingOverlayProps) {
  return (
    <div
      className={`uni-loading-overlay${fullPage ? ' uni-loading-overlay--full' : ''}`}
      role="status"
      aria-live="polite"
    >
      <span className="spinner-border spinner-border-sm" aria-hidden="true" />
      <span className="uni-loading-overlay__label">{label}</span>
    </div>
  )
}
