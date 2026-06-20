import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from '../layouts/AppShell'
import { ProtectedRoute } from './ProtectedRoute'
import PlatformOverviewPage from '../pages/PlatformOverviewPage'
import TenantsPage from '../pages/platform/TenantsPage'
import TenantWorkspacePage from '../pages/platform/TenantWorkspacePage'
import StoresPage from '../pages/platform/StoresPage'
import StoreWorkspacePage from '../pages/platform/StoreWorkspacePage'
import UsersPage from '../pages/platform/UsersPage'
import UserWorkspacePage from '../pages/platform/UserWorkspacePage'
import RolesPage from '../pages/platform/RolesPage'
import RoleWorkspacePage from '../pages/platform/RoleWorkspacePage'
import ModulesPage from '../pages/administration/ModulesPage'
import ModuleWorkspacePage from '../pages/administration/ModuleWorkspacePage'
import PermissionsPage from '../pages/administration/PermissionsPage'
import ReportsPage from '../pages/ReportsPage'
import SettingsPage from '../pages/SettingsPage'

export function AppRouter() {
  return (
    <Routes>
      <Route
        element={
          <ProtectedRoute>
            <AppShell />
          </ProtectedRoute>
        }
      >
        <Route index element={<Navigate to="/overview" replace />} />
        <Route path="/overview" element={<PlatformOverviewPage />} />
        <Route path="/platform/tenants" element={<TenantsPage />} />
        <Route path="/platform/tenants/:tenantId" element={<TenantWorkspacePage />} />
        <Route path="/platform/stores" element={<StoresPage />} />
        <Route path="/platform/stores/:storeId" element={<StoreWorkspacePage />} />
        <Route path="/platform/users" element={<UsersPage />} />
        <Route path="/platform/users/:userId" element={<UserWorkspacePage />} />
        <Route path="/platform/roles" element={<RolesPage />} />
        <Route path="/platform/roles/:roleId" element={<RoleWorkspacePage />} />
        <Route path="/administration/modules" element={<ModulesPage />} />
        <Route path="/administration/modules/:moduleId" element={<ModuleWorkspacePage />} />
        <Route path="/administration/permissions" element={<PermissionsPage />} />
        <Route path="/reports" element={<ReportsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/overview" replace />} />
      </Route>
    </Routes>
  )
}
