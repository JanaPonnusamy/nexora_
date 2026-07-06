import { useSearchParams } from 'react-router-dom'
import { ControlCenterTab } from '../../components/sync/ControlCenterTab'
import { LiveOperationsTab } from '../../components/sync/LiveOperationsTab'
import { TableStatisticsTab } from '../../components/sync/TableStatisticsTab'
import { SchedulesTab } from '../../components/sync/SchedulesTab'
import { TableConfigTab } from '../../components/sync/TableConfigTab'
import { ColumnMappingTab } from '../../components/sync/ColumnMappingTab'
import { StoreHealthTab } from '../../components/sync/StoreHealthTab'
import { SyncHistoryTab } from '../../components/sync/SyncHistoryTab'
import '../../components/sync/sync-ui.css'

type SyncTab = 'control' | 'live' | 'tablestats' | 'schedules' | 'tables' | 'mapping' | 'health' | 'history'

const TABS: { key: SyncTab; label: string; icon: string }[] = [
  { key: 'control', label: 'Control Center', icon: 'bi-speedometer2' },
  { key: 'live', label: 'Live Operations', icon: 'bi-broadcast-pin' },
  { key: 'tablestats', label: 'Table Statistics', icon: 'bi-bar-chart-line' },
  { key: 'schedules', label: 'Schedules', icon: 'bi-calendar-event' },
  { key: 'tables', label: 'Table Configuration', icon: 'bi-table' },
  { key: 'mapping', label: 'Column Mapping', icon: 'bi-diagram-3' },
  { key: 'health', label: 'Store Health', icon: 'bi-heart-pulse' },
  { key: 'history', label: 'Sync History', icon: 'bi-clock-history' },
]

const TAB_KEYS = TABS.map((t) => t.key)

export default function SyncAdministrationPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const param = searchParams.get('tab')
  const activeTab: SyncTab = (TAB_KEYS as string[]).includes(param ?? '')
    ? (param as SyncTab)
    : 'control'

  const setTab = (tab: SyncTab) =>
    setSearchParams(tab === 'control' ? {} : { tab }, { replace: true })

  return (
    <div className="sx container-fluid px-0">
      <div className="sx-head">
        <div>
          <div className="sx-head__crumb">Sync</div>
          <h1 className="sx-head__title">Sync Control Center</h1>
          <div className="sx-head__sub">
            Monitor agents, orchestrate delta sync and manage table configuration across every store.
          </div>
        </div>
      </div>

      <div className="sx-tabs" role="tablist" aria-label="Sync sections">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            role="tab"
            id={`tab-${tab.key}`}
            aria-selected={activeTab === tab.key}
            aria-controls={`panel-${tab.key}`}
            className={`sx-tab${activeTab === tab.key ? ' sx-tab--active' : ''}`}
            onClick={() => setTab(tab.key)}
          >
            <i className={`bi ${tab.icon}`} aria-hidden="true" />
            {tab.label}
          </button>
        ))}
      </div>

      <div role="tabpanel" id={`panel-${activeTab}`} aria-labelledby={`tab-${activeTab}`}>
        {activeTab === 'control' && <ControlCenterTab />}
        {activeTab === 'live' && <LiveOperationsTab />}
        {activeTab === 'tablestats' && <TableStatisticsTab />}
        {activeTab === 'schedules' && <SchedulesTab />}
        {activeTab === 'tables' && <TableConfigTab />}
        {activeTab === 'mapping' && <ColumnMappingTab />}
        {activeTab === 'health' && <StoreHealthTab />}
        {activeTab === 'history' && <SyncHistoryTab />}
      </div>
    </div>
  )
}
