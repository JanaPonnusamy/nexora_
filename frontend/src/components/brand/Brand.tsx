import { Link } from 'react-router-dom'
import logoLockup from '../../assets/axythic-logo.svg'
import logoMark from '../../assets/axythic-mark.svg'
import { APP_NAME } from '../../utils/appInfo'

interface BrandProps {
  /** Where the brand links to. Omit to render as plain, non-interactive marks. */
  to?: string
}

/**
 * Axythic company lockup plus the product name.
 *
 * The lockup already carries a wordmark, so the product sits beside it as a
 * quiet label rather than a second wordmark competing with it. Below `sm` the
 * lockup swaps to the mark alone and the product label drops away.
 *
 * To swap in an updated asset, replace `assets/axythic-logo.svg` (and the
 * matching `axythic-mark.svg`) — nothing here needs to change.
 */
export function Brand({ to = '/' }: BrandProps) {
  const content = (
    <>
      <img className="app-brand__lockup" src={logoLockup} alt="Axythic" />
      <img className="app-brand__mark" src={logoMark} alt="Axythic" />
      <span className="app-brand__rule" aria-hidden="true" />
      <span className="app-brand__product">{APP_NAME}</span>
    </>
  )

  if (!to) {
    return <span className="app-brand">{content}</span>
  }

  return (
    <Link className="app-brand" to={to} aria-label={`Axythic ${APP_NAME} — home`}>
      {content}
    </Link>
  )
}
