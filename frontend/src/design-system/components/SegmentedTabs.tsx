interface SegmentedTabItem<T extends string> {
  value: T
  label: string
  description?: string
  icon?: string
}

interface SegmentedTabsProps<T extends string> {
  items: SegmentedTabItem<T>[]
  activeValue: T
  ariaLabel: string
  onChange: (value: T) => void
  // Slim, single-line pill row (no description subtitle, no min-height) for
  // dense workspaces where the tabs sit above the actual content — e.g. the
  // Purchase Workspace, where the product grid is the point of the page and
  // the default card-style tabs (5rem min-height each) were stealing the
  // height the grid needed.
  compact?: boolean
}

export function SegmentedTabs<T extends string>({
  items,
  activeValue,
  ariaLabel,
  onChange,
  compact = false,
}: SegmentedTabsProps<T>) {
  return (
    <div
      className={`ds-segmented-tabs${compact ? ' ds-segmented-tabs--compact' : ''}`}
      role="tablist"
      aria-label={ariaLabel}
    >
      {items.map((item) => {
        const active = item.value === activeValue
        return (
          <button
            key={item.value}
            type="button"
            role="tab"
            aria-selected={active}
            title={compact ? item.description : undefined}
            className={`ds-segmented-tabs__tab${active ? ' is-active' : ''}`}
            onClick={() => onChange(item.value)}
          >
            {item.icon && (
              <span className="ds-segmented-tabs__icon" aria-hidden="true">
                <i className={`bi ${item.icon}`} />
              </span>
            )}
            <span className="ds-segmented-tabs__copy">
              <strong>{item.label}</strong>
              {!compact && item.description && <small>{item.description}</small>}
            </span>
          </button>
        )
      })}
    </div>
  )
}
