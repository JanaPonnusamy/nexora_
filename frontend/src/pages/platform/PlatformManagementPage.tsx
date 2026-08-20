import { useSearchParams } from 'react-router-dom'
import { PageHeader } from '../../components/common/PageHeader'
import { SegmentedTabs } from '../../design-system/components/SegmentedTabs'
import { WorkspaceContainer } from '../../design-system/components/WorkspaceContainer'
import TenantsPage from './TenantsPage'
import StoresPage from './StoresPage'
import UsersPage from './UsersPage'
import RolesPage from './RolesPage'

const tabs = [
  { id: 'tenants', label: 'Tenants', icon: 'bi-building', description: 'Organizations' },
  { id: 'stores', label: 'Stores', icon: 'bi-shop', description: 'Locations' },
  { id: 'users', label: 'Users', icon: 'bi-people', description: 'Team access' },
  { id: 'roles', label: 'Roles', icon: 'bi-person-badge', description: 'Permissions' },
] as const

type TabId = (typeof tabs)[number]['id']

function isTabId(value: string | null): value is TabId {
  return tabs.some((tab) => tab.id === value)
}

export default function PlatformManagementPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const requestedTab = searchParams.get('tab')
  const activeTab: TabId = isTabId(requestedTab) ? requestedTab : 'tenants'

  const selectTab = (tab: TabId) => setSearchParams(tab === 'tenants' ? {} : { tab })

  return (
    <WorkspaceContainer className="platform-management">
      <PageHeader
        title="Platform Management"
        breadcrumb={['Platform', 'Management']}
        description="Manage organizations, locations, people, and access from one operational workspace."
      />
      <SegmentedTabs
        items={tabs.map((tab) => ({
          value: tab.id,
          label: tab.label,
          description: tab.description,
          icon: tab.icon,
        }))}
        activeValue={activeTab}
        ariaLabel="Platform management sections"
        onChange={selectTab}
      />
      <section
        id={`platform-panel-${activeTab}`}
        className="platform-management__panel"
        role="tabpanel"
        aria-label={tabs.find((tab) => tab.id === activeTab)?.label}
      >
        {activeTab === 'tenants' && <TenantsPage embedded />}
        {activeTab === 'stores' && <StoresPage embedded />}
        {activeTab === 'users' && <UsersPage embedded />}
        {activeTab === 'roles' && <RolesPage embedded />}
      </section>
    </WorkspaceContainer>
  )
}
