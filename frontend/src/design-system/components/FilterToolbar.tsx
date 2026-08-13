import { FilterAction, FilterBar, FilterSearch, FilterSelect } from './FilterBar'

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
    <FilterBar className="list-toolbar">
      <FilterSearch
        className="list-toolbar__search"
        placeholder={searchPlaceholder}
        ariaLabel={searchAriaLabel}
        value={searchValue}
        onChange={onSearchChange}
      />

      {filters.map((filter) => (
        <FilterSelect
          key={filter.key}
          className="list-toolbar__filter"
          ariaLabel={filter.ariaLabel}
          value={filter.value}
          onChange={filter.onChange}
          options={filter.options}
        />
      ))}

      <FilterAction className="ms-auto" label={actionLabel} icon={actionIcon} onClick={onAction} />
    </FilterBar>
  )
}
