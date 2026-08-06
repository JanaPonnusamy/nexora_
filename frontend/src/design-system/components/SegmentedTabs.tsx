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
}

export function SegmentedTabs<T extends string>({
  items,
  activeValue,
  ariaLabel,
  onChange,
}: SegmentedTabsProps<T>) {
  return (
    <div className="ds-segmented-tabs" role="tablist" aria-label={ariaLabel}>
      {items.map((item) => {
        const active = item.value === activeValue
        return (
          <button
            key={item.value}
            type="button"
            role="tab"
            aria-selected={active}
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
              {item.description && <small>{item.description}</small>}
            </span>
          </button>
        )
      })}
    </div>
  )
}
