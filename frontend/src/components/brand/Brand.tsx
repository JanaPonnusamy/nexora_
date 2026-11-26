import { Link } from 'react-router-dom'
import logoMark from '../../assets/nextech-mediq-mark.svg'

interface BrandProps {
  /** Where the brand links to. Omit to render as plain, non-interactive marks. */
  to?: string
}

/**
 * NexTech MediQ identity used throughout the application shell. The lockup is
 * the mark plus live text so the "AI-Powered" caption stays legible and follows
 * the theme.
 */
export function Brand({ to = '/' }: BrandProps) {
  const content = (
    <>
      <span className="app-brand__lockup">
        <img className="app-brand__lockup-mark" src={logoMark} alt="" aria-hidden="true" />
        <span className="app-brand__text">
          <span className="app-brand__name">NexTech <b>MediQ</b></span>
          <span className="app-brand__ai"><i aria-hidden="true">✦</i> AI-Powered Workspace</span>
        </span>
      </span>
      <img className="app-brand__mark" src={logoMark} alt="" aria-hidden="true" />
    </>
  )

  if (!to) {
    return <span className="app-brand" aria-label="NexTech MediQ, AI-Powered">{content}</span>
  }

  return (
    <Link className="app-brand" to={to} aria-label="NexTech MediQ — home">
      {content}
    </Link>
  )
}
