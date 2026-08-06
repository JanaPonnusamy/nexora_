import type { ChangeEvent } from 'react'

export interface ToolbarOption {
  label: string
  value: string
}

export interface ToolbarFilter {
  key: string
  ariaLabel: string
  value: string
  onChange: (value: string) => void
  options: ToolbarOption[]
}

interface FilterToolbarProps {
  searchPlaceholder: string
  searchAriaLabel: string
  searchValue: string
  onSearchChange: (value: string) => void
  filters?: ToolbarFilter[]
  actionLabel: string
  actionIcon?: string
  onAction: () => void
}

export function FilterToolbar({
  searchPlaceholder,
  searchAriaLabel,
  searchValue,
  onSearchChange,
  filters = [],
  actionLabel,
  actionIcon = 'bi-plus-lg',
  onAction,
}: FilterToolbarProps) {
  return (
    <div className="ds-toolbar list-toolbar">
      <label className="ds-search-field list-toolbar__search">
        <i className="bi bi-search" aria-hidden="true" />
        <input
          type="search"
          className="form-control"
          placeholder={searchPlaceholder}
          aria-label={searchAriaLabel}
          value={searchValue}
          onChange={(event: ChangeEvent<HTMLInputElement>) => onSearchChange(event.target.value)}
        />
      </label>

      {filters.map((filter) => (
        <select
          key={filter.key}
          className="form-select list-toolbar__filter ds-toolbar__filter"
          aria-label={filter.ariaLabel}
          value={filter.value}
          onChange={(event: ChangeEvent<HTMLSelectElement>) => filter.onChange(event.target.value)}
        >
          {filter.options.map((option) => (
            <option key={`${filter.key}-${option.value}`} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      ))}

      <button type="button" className="btn btn-primary ds-button ds-button--primary ms-auto" onClick={onAction}>
        {actionIcon && <i className={`bi ${actionIcon} me-1`} aria-hidden="true" />}
        {actionLabel}
      </button>
    </div>
  )
}
