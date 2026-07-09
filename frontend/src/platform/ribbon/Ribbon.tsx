import { useState } from 'react'
import type { RibbonContribution } from '../modules/types'

interface RibbonProps {
  contributions: RibbonContribution[]
}

const HOME_TAB = 'Home'
const HELP_TAB = 'Help'

/**
 * Modules contribute tabs/groups/commands (RibbonContribution); Home and
 * Help are the only platform-owned tabs — no module-specific buttons are
 * hardcoded here.
 */
export function Ribbon({ contributions }: RibbonProps) {
  const tabs = [HOME_TAB, ...contributions.map((c) => c.tab), HELP_TAB]
  const [activeTab, setActiveTab] = useState(HOME_TAB)
  const resolvedActiveTab = tabs.includes(activeTab) ? activeTab : HOME_TAB
  const activeContribution = contributions.find((c) => c.tab === resolvedActiveTab)

  return (
    <div className="platform-ribbon">
      <div className="platform-ribbon__tabs" role="tablist">
        {tabs.map((tab) => (
          <button
            key={tab}
            type="button"
            role="tab"
            aria-selected={tab === resolvedActiveTab}
            className={`platform-ribbon__tab${tab === resolvedActiveTab ? ' is-active' : ''}`}
            onClick={() => setActiveTab(tab)}
          >
            {tab}
          </button>
        ))}
      </div>
      <div className="platform-ribbon__groups" role="tabpanel">
        {resolvedActiveTab === HOME_TAB && (
          <div className="platform-ribbon__empty">Home commands appear here as modules contribute them.</div>
        )}
        {resolvedActiveTab === HELP_TAB && <div className="platform-ribbon__empty">Help &amp; About</div>}
        {activeContribution?.groups.map((group) => (
          <div key={group.id} className="platform-ribbon__group">
            <div className="platform-ribbon__commands">
              {group.commands.map((command) => (
                <button
                  key={command.id}
                  type="button"
                  className="platform-ribbon__command"
                  title={command.shortcut ? `${command.label} (${command.shortcut})` : command.label}
                  onClick={command.onExecute}
                >
                  {command.icon && <i className={`bi ${command.icon}`} aria-hidden="true" />}
                  <span>{command.label}</span>
                </button>
              ))}
            </div>
            <div className="platform-ribbon__group-label">{group.label}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
