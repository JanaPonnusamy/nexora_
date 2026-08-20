import { useState } from 'react'
import type { ReactNode } from 'react'

interface InspectorTab {
  id: string
  label: string
  content: ReactNode
}

interface InspectorPanelProps {
  title: string
  summary?: ReactNode
  actions?: ReactNode
  tabs?: InspectorTab[]
  defaultTabId?: string
  children?: ReactNode
  empty?: boolean
  emptyTitle?: string
  emptyDescription?: string
}

export function InspectorPanel({
  title,
  summary,
  actions,
  tabs,
  defaultTabId,
  children,
  empty = false,
  emptyTitle = 'Nothing selected',
  emptyDescription = 'Choose a record to inspect details here.',
}: InspectorPanelProps) {
  const firstTab = tabs?.[0]?.id ?? defaultTabId ?? 'summary'
  const [activeTab, setActiveTab] = useState(firstTab)
  const activeContent = tabs?.find((tab) => tab.id === activeTab)?.content

  return (
    <aside className="ds-inspector">
      <header className="ds-inspector__head">
        <div>
          <h3 className="ds-inspector__title">{title}</h3>
          {summary && <div className="ds-inspector__summary">{summary}</div>}
        </div>
        {actions && <div className="ds-inspector__actions">{actions}</div>}
      </header>

      {tabs && tabs.length > 0 && (
        <div className="ds-inspector__tabs" role="tablist" aria-label={`${title} tabs`}>
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={tab.id === activeTab}
              className={`ds-inspector__tab${tab.id === activeTab ? ' is-active' : ''}`}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      )}

      <div className="ds-inspector__body">
        {empty ? (
          <div className="ds-inspector__empty">
            <strong>{emptyTitle}</strong>
            <p>{emptyDescription}</p>
          </div>
        ) : (
          activeContent ?? children
        )}
      </div>
    </aside>
  )
}
