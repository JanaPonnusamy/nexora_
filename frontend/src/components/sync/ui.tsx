import type { ChangeEvent, ReactNode } from 'react'

export type Tone =
  | 'indigo' | 'teal' | 'success' | 'danger' | 'warning' | 'info' | 'violet' | 'muted'

/* ---- Card ---------------------------------------------------------------- */

export function SxCard({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`sx-card ${className}`}>{children}</div>
}

export function SxCardHead({
  title, icon, sub, action,
}: { title: string; icon?: string; sub?: ReactNode; action?: ReactNode }) {
  return (
    <div className="sx-card__head">
      <div className="d-flex align-items-center gap-2 flex-wrap">
        <h3 className="sx-card__title">
          {icon && <i className={`bi ${icon}`} aria-hidden="true" />}
          {title}
        </h3>
        {sub && <span className="sx-card__sub">{sub}</span>}
      </div>
      {action}
    </div>
  )
}

export function SxCardBody({ children, flush = false }: { children: ReactNode; flush?: boolean }) {
  return <div className={`sx-card__body${flush ? ' sx-card__body--flush' : ''}`}>{children}</div>
}

/* ---- Stat tile ----------------------------------------------------------- */

export function SxStat({
  icon, tone, value, label, sub,
}: { icon: string; tone: Tone; value: ReactNode; label: string; sub?: ReactNode }) {
  return (
    <div className={`sx-stat sx-tone-${tone}`}>
      <span className="sx-stat__icon"><i className={`bi ${icon}`} aria-hidden="true" /></span>
      <div className="min-w-0">
        <div className="sx-stat__value">{value}</div>
        <div className="sx-stat__label">{label}</div>
        {sub != null && <div className="sx-stat__sub">{sub}</div>}
      </div>
    </div>
  )
}

/* ---- Chip ---------------------------------------------------------------- */

export function SxChip({
  children, tone, dot = false, running = false,
}: { children: ReactNode; tone?: Tone | 'default'; dot?: boolean; running?: boolean }) {
  const cls = tone && tone !== 'default' ? ` sx-chip--${tone}` : ''
  return (
    <span className={`sx-chip${cls}${running ? ' sx-chip--running' : ''}`}>
      {dot && <span className="sx-chip__dot" />}
      {children}
    </span>
  )
}

/* ---- Buttons ------------------------------------------------------------- */

type BtnVariant = 'primary' | 'ghost' | 'success' | 'warning' | 'danger'
export function SxButton({
  children, variant = 'ghost', icon, sm = false, disabled, onClick, title, busy = false,
}: {
  children?: ReactNode; variant?: BtnVariant; icon?: string; sm?: boolean
  disabled?: boolean; onClick?: () => void; title?: string; busy?: boolean
}) {
  return (
    <button
      type="button"
      className={`sx-btn sx-btn--${variant}${sm ? ' sx-btn--sm' : ''}${children ? '' : ' sx-btn--icon'}`}
      disabled={disabled || busy}
      onClick={onClick}
      title={title}
    >
      {busy ? <span className="spinner-border spinner-border-sm" aria-hidden="true" />
        : icon && <i className={`bi ${icon}`} aria-hidden="true" />}
      {children}
    </button>
  )
}

/* ---- Search + Select ----------------------------------------------------- */

export function SxSearch({
  value, onChange, placeholder = 'Search…', ariaLabel,
}: { value: string; onChange: (v: string) => void; placeholder?: string; ariaLabel?: string }) {
  return (
    <span className="sx-search">
      <i className="bi bi-search" aria-hidden="true" />
      <input
        type="search"
        value={value}
        placeholder={placeholder}
        aria-label={ariaLabel ?? placeholder}
        onChange={(e: ChangeEvent<HTMLInputElement>) => onChange(e.target.value)}
      />
    </span>
  )
}

export function SxSelect({
  value, onChange, ariaLabel, children,
}: { value: string; onChange: (v: string) => void; ariaLabel: string; children: ReactNode }) {
  return (
    <select
      className="sx-select"
      aria-label={ariaLabel}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      {children}
    </select>
  )
}

/* ---- Segmented control --------------------------------------------------- */

export function SxSegmented<T extends string>({
  options, value, onChange, ariaLabel,
}: {
  options: { label: string; value: T }[]
  value: T
  onChange: (v: T) => void
  ariaLabel: string
}) {
  return (
    <div className="sx-seg" role="group" aria-label={ariaLabel}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          className={`sx-seg__btn${value === o.value ? ' sx-seg__btn--active' : ''}`}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

/* ---- Progress ------------------------------------------------------------ */

export function SxProgress({ value, animated = true }: { value: number; animated?: boolean }) {
  const pct = Math.min(100, Math.max(0, value))
  return (
    <div className="sx-progress" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
      <div
        className={`sx-progress__bar${animated && pct < 100 ? ' sx-progress__bar--anim' : ''}`}
        style={{ width: `${Math.max(3, pct)}%` }}
      />
    </div>
  )
}

/* ---- Table scaffold ------------------------------------------------------ */

export function SxTable({ children }: { children: ReactNode }) {
  return (
    <div className="sx-tablewrap">
      <table className="sx-table">{children}</table>
    </div>
  )
}

/* ---- Pager --------------------------------------------------------------- */

export function SxPager({
  rangeStart, rangeEnd, total, page, totalPages, onPage, noun = 'items',
}: {
  rangeStart: number; rangeEnd: number; total: number
  page: number; totalPages: number; onPage: (p: number) => void; noun?: string
}) {
  return (
    <div className="sx-pager">
      <span>Showing {rangeStart}–{rangeEnd} of {total.toLocaleString()} {noun}</span>
      <div className="sx-pager__group">
        <button type="button" className="sx-pager__btn" disabled={page === 0} onClick={() => onPage(page - 1)} aria-label="Previous page">
          <i className="bi bi-chevron-left" aria-hidden="true" />
        </button>
        <span className="sx-pager__page">{page + 1} / {totalPages}</span>
        <button type="button" className="sx-pager__btn" disabled={page >= totalPages - 1} onClick={() => onPage(page + 1)} aria-label="Next page">
          <i className="bi bi-chevron-right" aria-hidden="true" />
        </button>
      </div>
    </div>
  )
}

/* ---- Live badge ---------------------------------------------------------- */

export function SxLive({ label }: { label: string }) {
  return (
    <span className="sx-live"><span className="sx-live__dot" />{label}</span>
  )
}

/* ---- Donut panel legend -------------------------------------------------- */

export function SxLegend({
  segments,
}: { segments: { label: string; value: number; color: string }[] }) {
  const total = segments.reduce((a, s) => a + s.value, 0)
  return (
    <div className="sx-legend">
      {segments.map((s) => (
        <div key={s.label} className="sx-legend__row">
          <span className="sx-legend__dot" style={{ background: s.color }} />
          <span className="sx-legend__label">{s.label}</span>
          <span className="sx-legend__val">{s.value.toLocaleString()}</span>
          <span className="sx-legend__pct">{total ? `${((s.value / total) * 100).toFixed(0)}%` : '0%'}</span>
        </div>
      ))}
    </div>
  )
}
