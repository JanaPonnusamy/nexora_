import { Link } from 'react-router-dom'
import logoLockup from '../../assets/axythic-logo.svg'
import logoMark from '../../assets/axythic-mark.svg'

interface BrandProps {
  /** Where the brand links to. Omit to render as plain, non-interactive marks. */
  to?: string
}

/** Axythic identity used throughout the application shell. */
export function Brand({ to = '/' }: BrandProps) {
  const content = (
    <>
      <img className="app-brand__lockup" src={logoLockup} alt="Axythic" />
      <img className="app-brand__mark" src={logoMark} alt="" aria-hidden="true" />
    </>
  )

  if (!to) {
    return <span className="app-brand">{content}</span>
  }

  return (
    <Link className="app-brand" to={to} aria-label="Axythic — home">
      {content}
    </Link>
  )
}
