import { useSearchParams } from 'react-router-dom'
import { PageHeader } from '../../components/common/PageHeader'
import { ControlCenterTab } from '../../components/sync/ControlCenterTab'
import { SchedulesTab } from '../../components/sync/SchedulesTab'
import { TableConfigTab } from '../../components/sync/TableConfigTab'
import { ColumnMappingTab } from '../../components/sync/ColumnMappingTab'
import { StoreHealthTab } from '../../components/sync/StoreHealthTab'
import { SyncHistoryTab } from '../../components/sync/SyncHistoryTab'

type SyncTab = 'control' | 'schedules' | 'tables' | 'mapping' | 'health' | 'history'

const TABS: { key: SyncTab; label: string; icon: string }[] = [
  { key: 'control', label: 'Control Center', icon: 'bi-speedometer2' },
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
    <div className="container-fluid px-0">
      <PageHeader title="Sync Administration" breadcrumb={['Sync Administration']} />

      <ul className="nav nav-tabs mb-3 flex-nowrap overflow-auto" role="tablist">
        {TABS.map((tab) => (
          <li className="nav-item" key={tab.key} role="presentation">
            <button
              type="button"
              role="tab"
              id={`tab-${tab.key}`}
              aria-selected={activeTab === tab.key}
              aria-controls={`panel-${tab.key}`}
              className={`nav-link text-nowrap${activeTab === tab.key ? ' active' : ''}`}
              onClick={() => setTab(tab.key)}
            >
              <i className={`bi ${tab.icon} me-1`} aria-hidden="true" />
              {tab.label}
            </button>
          </li>
        ))}
      </ul>

      <div role="tabpanel" id={`panel-${activeTab}`} aria-labelledby={`tab-${activeTab}`}>
        {activeTab === 'control' && <ControlCenterTab />}
        {activeTab === 'schedules' && <SchedulesTab />}
        {activeTab === 'tables' && <TableConfigTab />}
        {activeTab === 'mapping' && <ColumnMappingTab />}
        {activeTab === 'health' && <StoreHealthTab />}
        {activeTab === 'history' && <SyncHistoryTab />}
      </div>
    </div>
  )
}
