import type { ChangeEvent, ReactNode, Ref } from 'react'

export interface FilterOption<T extends string = string> {
  value: T
  label: ReactNode
  disabled?: boolean
}

type FilterBarProps = {
  children: ReactNode
  className?: string
  compact?: boolean
  stacked?: boolean
  ariaLabel?: string
}

export function FilterBar({ children, className = '', compact = false, stacked = false, ariaLabel = 'Filters' }: FilterBarProps) {
  const classes = [
    'ds-filter-bar',
    compact && 'ds-filter-bar--compact',
    stacked && 'ds-filter-bar--stacked',
    className,
  ].filter(Boolean).join(' ')

  return <div className={classes} role="search" aria-label={ariaLabel}>{children}</div>
}

type FilterSearchProps = {
  value: string
  onChange: (value: string) => void
  placeholder: string
  ariaLabel: string
  icon?: string
  className?: string
  disabled?: boolean
  inputRef?: Ref<HTMLInputElement>
  autoFocus?: boolean
}

export function FilterSearch({
  value,
  onChange,
  placeholder,
  ariaLabel,
  icon = 'bi-search',
  className = '',
  disabled = false,
  inputRef,
  autoFocus = false,
}: FilterSearchProps) {
  return (
    <label className={`ds-filter-search ${className}`.trim()}>
      <i className={`bi ${icon}`} aria-hidden="true" />
      <input
        ref={inputRef}
        type="search"
        value={value}
        placeholder={placeholder}
        aria-label={ariaLabel}
        disabled={disabled}
        autoFocus={autoFocus}
        onChange={(event: ChangeEvent<HTMLInputElement>) => onChange(event.target.value)}
      />
    </label>
  )
}

type FilterTabsProps<T extends string> = {
  value: T
  onChange: (value: T) => void
  options: readonly FilterOption<T>[]
  ariaLabel: string
  className?: string
  disabled?: boolean
}

export function FilterTabs<T extends string>({ value, onChange, options, ariaLabel, className = '', disabled = false }: FilterTabsProps<T>) {
  return (
    <div className={`ds-filter-tabs ${className}`.trim()} role="tablist" aria-label={ariaLabel}>
      {options.map((option) => {
        const active = option.value === value
        return (
          <button
            key={option.value}
            type="button"
            role="tab"
            aria-selected={active}
            className={active ? 'is-active' : undefined}
            disabled={disabled || option.disabled}
            onClick={() => onChange(option.value)}
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}

type FilterSelectProps<T extends string = string> = {
  value: T
  onChange: (value: T) => void
  ariaLabel: string
  options?: readonly FilterOption<T>[]
  children?: ReactNode
  label?: ReactNode
  className?: string
  disabled?: boolean
  title?: string
}

export function FilterSelect<T extends string = string>({
  value,
  onChange,
  ariaLabel,
  options,
  children,
  label,
  className = '',
  disabled = false,
  title,
}: FilterSelectProps<T>) {
  const select = (
    <select
      className={`ds-filter-select ${className}`.trim()}
      value={value}
      aria-label={ariaLabel}
      disabled={disabled}
      title={title}
      onChange={(event: ChangeEvent<HTMLSelectElement>) => onChange(event.target.value as T)}
    >
      {options?.map((option) => (
        <option key={option.value} value={option.value} disabled={option.disabled}>{option.label}</option>
      ))}
      {children}
    </select>
  )

  return label ? <label className="ds-filter-field"><span>{label}</span>{select}</label> : select
}

type FilterFieldProps = {
  label: ReactNode
  children: ReactNode
  className?: string
}

export function FilterField({ label, children, className = '' }: FilterFieldProps) {
  return <label className={`ds-filter-field ${className}`.trim()}><span>{label}</span>{children}</label>
}

type FilterActionProps = {
  label: string
  onClick: () => void
  icon?: string
  variant?: 'primary' | 'secondary' | 'warning'
  disabled?: boolean
  title?: string
  className?: string
}

export function FilterAction({
  label,
  onClick,
  icon,
  variant = 'primary',
  disabled = false,
  title,
  className = '',
}: FilterActionProps) {
  return (
    <button
      type="button"
      className={`ds-filter-action ds-filter-action--${variant} ${className}`.trim()}
      disabled={disabled}
      title={title}
      onClick={onClick}
    >
      {icon && <i className={`bi ${icon}`} aria-hidden="true" />}
      {label}
    </button>
  )
}

export function FilterBarEnd({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`ds-filter-bar__end ${className}`.trim()}>{children}</div>
}
