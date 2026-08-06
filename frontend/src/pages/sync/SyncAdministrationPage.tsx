import { useSearchParams } from 'react-router-dom'
import { PageHeader } from '../../components/common/PageHeader'
import { ControlCenterTab } from '../../components/sync/ControlCenterTab'
import { LiveOperationsTab } from '../../components/sync/LiveOperationsTab'
import { TableStatisticsTab } from '../../components/sync/TableStatisticsTab'
import { SchedulesTab } from '../../components/sync/SchedulesTab'
import { TableConfigTab } from '../../components/sync/TableConfigTab'
import { ColumnMappingTab } from '../../components/sync/ColumnMappingTab'
import { StoreHealthTab } from '../../components/sync/StoreHealthTab'
import { SyncHistoryTab } from '../../components/sync/SyncHistoryTab'
import { AgentOpsTab } from '../../components/sync/AgentOpsTab'
import { SegmentedTabs } from '../../design-system/components/SegmentedTabs'
import { WorkspaceShell } from '../../design-system/components/WorkspaceShell'
import '../../components/sync/sync-ui.css'

type SyncTab =
  | 'control'
  | 'live'
  | 'tablestats'
  | 'schedules'
  | 'tables'
  | 'mapping'
  | 'health'
  | 'history'
  | 'agentops'

const TABS: { key: SyncTab; label: string; icon: string }[] = [
  { key: 'control', label: 'Dashboard', icon: 'bi-speedometer2' },
  { key: 'live', label: 'Live', icon: 'bi-broadcast-pin' },
  { key: 'tablestats', label: 'Tables', icon: 'bi-bar-chart-line' },
  { key: 'schedules', label: 'Schedules', icon: 'bi-calendar-event' },
  { key: 'tables', label: 'Config', icon: 'bi-table' },
  { key: 'mapping', label: 'Mapping', icon: 'bi-diagram-3' },
  { key: 'health', label: 'Store Health', icon: 'bi-heart-pulse' },
  { key: 'history', label: 'Sync History', icon: 'bi-clock-history' },
  { key: 'agentops', label: 'Agents', icon: 'bi-router' },
]

const TAB_KEYS = TABS.map((tab) => tab.key)

export default function SyncAdministrationPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const param = searchParams.get('tab')
  const activeTab: SyncTab = (TAB_KEYS as string[]).includes(param ?? '')
    ? (param as SyncTab)
    : 'control'

  const setTab = (tab: SyncTab) =>
    setSearchParams(tab === 'control' ? {} : { tab }, { replace: true })

  return (
    <WorkspaceShell
      fullWidth
      className="sx sx--compact sx-shell"
      header={
        <PageHeader
          title="Sync Control Center"
          breadcrumb={['Operations', 'Sync']}
          description="Monitor agents, orchestrate delta sync, and manage table configuration across every store."
        />
      }
      filters={
        <SegmentedTabs
          items={TABS.map((tab) => ({
            value: tab.key,
            label: tab.label,
            icon: tab.icon,
          }))}
          activeValue={activeTab}
          ariaLabel="Sync sections"
          onChange={setTab}
        />
      }
    >
      <div role="tabpanel" id={`panel-${activeTab}`} aria-labelledby={`tab-${activeTab}`}>
        {activeTab === 'control' && <ControlCenterTab />}
        {activeTab === 'live' && <LiveOperationsTab />}
        {activeTab === 'tablestats' && <TableStatisticsTab />}
        {activeTab === 'schedules' && <SchedulesTab />}
        {activeTab === 'tables' && <TableConfigTab />}
        {activeTab === 'mapping' && <ColumnMappingTab />}
        {activeTab === 'health' && <StoreHealthTab />}
        {activeTab === 'history' && <SyncHistoryTab />}
        {activeTab === 'agentops' && <AgentOpsTab />}
      </div>
    </WorkspaceShell>
  )
}
