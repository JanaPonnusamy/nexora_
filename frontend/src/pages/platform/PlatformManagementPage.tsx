import { useSearchParams } from 'react-router-dom'
import { PageHeader } from '../../components/common/PageHeader'
import TenantsPage from './TenantsPage'
import StoresPage from './StoresPage'
import UsersPage from './UsersPage'
import RolesPage from './RolesPage'
import './platform-management.css'

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
    <div className="container-fluid px-0 platform-management">
      <PageHeader
        title="Platform Management"
        breadcrumb={['Platform', 'Management']}
      />
      <p className="text-body-secondary mt-n3 mb-3">
        Manage organizations, locations, people, and access from one workspace.
      </p>
      <div className="platform-management__tabs" role="tablist" aria-label="Platform management sections">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={activeTab === tab.id}
            aria-controls={`platform-panel-${tab.id}`}
            className={`platform-management__tab${activeTab === tab.id ? ' is-active' : ''}`}
            onClick={() => selectTab(tab.id)}
          >
            <i className={`bi ${tab.icon}`} aria-hidden="true" />
            <span><strong>{tab.label}</strong><small>{tab.description}</small></span>
          </button>
        ))}
      </div>
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
    </div>
  )
}
