import { createBrowserRouter, createRoutesFromElements, Navigate, Route } from 'react-router-dom'
import { AppShell } from '../layouts/AppShell'
import { ProtectedRoute } from './ProtectedRoute'
import { RequireCapability } from './RequireCapability'
import { useAccess } from '../hooks/useAccess'
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
import SyncAdministrationPage from '../pages/sync/SyncAdministrationPage'
import ProductMappingPage from '../pages/mapping/ProductMappingPage'
import StockAvailabilityPage from '../pages/stock/StockAvailabilityPage'
import PurchaseWorkspacePage from '../pages/procurement/PurchaseWorkspacePage'
import ProductIntelligencePage from '../pages/procurement/ProductIntelligencePage'
import RefreshLauncherPage from '../pages/procurement/RefreshLauncherPage'
import CycleManagementPage from '../pages/procurement/CycleManagementPage'
import RefreshManagementPage from '../pages/procurement/RefreshManagementPage'
import CycleRefreshConsolePage from '../pages/procurement/CycleRefreshConsolePage'
import RefreshComparePage from '../pages/procurement/RefreshComparePage'
import PermissionsPage from '../pages/administration/PermissionsPage'
import ReportsPage from '../pages/ReportsPage'
import PassGenPage from '../pages/pass-gen/PassGenPage'
import LegacyOrderPage from '../pages/legacy-order/LegacyOrderPage'
import SettingsPage from '../pages/SettingsPage'
import PlatformShellPreviewPage from '../pages/PlatformShellPreviewPage'
import DocumentExtractionReviewPage from '../pages/document-extraction/ReviewPage'
import DocumentExtractionHistoryPage from '../pages/document-extraction/HistoryPage'

/** Sends the user to their role's landing page (Purchase Managers open directly
 *  into the Purchase Manager workspace). */
function RoleLanding() {
  const { landingPath } = useAccess()
  return <Navigate to={landingPath} replace />
}

export const appRouter = createBrowserRouter(
  createRoutesFromElements(
    <>
      {/* Desktop Platform shell preview — a separate top-level route (not
          nested under AppShell) so the new shell can be built and compared
          side-by-side without touching the existing app. */}
      <Route
        path="/platform-shell-preview"
        element={
          <ProtectedRoute>
            <PlatformShellPreviewPage />
          </ProtectedRoute>
        }
      />
      <Route
        element={
          <ProtectedRoute>
            <AppShell />
          </ProtectedRoute>
        }
      >
        <Route index element={<RoleLanding />} />
        <Route path="/overview" element={<RequireCapability cap="PLATFORM"><PlatformOverviewPage /></RequireCapability>} />
        <Route path="/platform/tenants" element={<RequireCapability cap="PLATFORM"><TenantsPage /></RequireCapability>} />
        <Route path="/platform/tenants/:tenantId" element={<RequireCapability cap="PLATFORM"><TenantWorkspacePage /></RequireCapability>} />
        <Route path="/platform/stores" element={<RequireCapability cap="PLATFORM"><StoresPage /></RequireCapability>} />
        <Route path="/platform/stores/:storeId" element={<RequireCapability cap="PLATFORM"><StoreWorkspacePage /></RequireCapability>} />
        <Route path="/platform/users" element={<RequireCapability cap="PLATFORM"><UsersPage /></RequireCapability>} />
        <Route path="/platform/users/:userId" element={<RequireCapability cap="PLATFORM"><UserWorkspacePage /></RequireCapability>} />
        <Route path="/platform/roles" element={<RequireCapability cap="PLATFORM"><RolesPage /></RequireCapability>} />
        <Route path="/platform/roles/:roleId" element={<RequireCapability cap="PLATFORM"><RoleWorkspacePage /></RequireCapability>} />
        <Route path="/administration/modules" element={<RequireCapability cap="ADMINISTRATION"><ModulesPage /></RequireCapability>} />
        <Route path="/administration/modules/:moduleId" element={<RequireCapability cap="ADMINISTRATION"><ModuleWorkspacePage /></RequireCapability>} />
        <Route path="/administration/permissions" element={<RequireCapability cap="ADMINISTRATION"><PermissionsPage /></RequireCapability>} />
        <Route path="/sync-administration" element={<RequireCapability cap="SYNC"><SyncAdministrationPage /></RequireCapability>} />
        <Route path="/product-mapping" element={<RequireCapability cap="PRODUCT_MAPPING"><ProductMappingPage /></RequireCapability>} />
        <Route path="/stock-availability" element={<RequireCapability cap="INVENTORY"><StockAvailabilityPage /></RequireCapability>} />
        <Route path="/procurement/console" element={<RequireCapability cap="PROCUREMENT_ADMIN"><CycleRefreshConsolePage /></RequireCapability>} />
        <Route path="/procurement/cycles" element={<RequireCapability cap="PROCUREMENT_ADMIN"><CycleManagementPage /></RequireCapability>} />
        <Route path="/procurement/refreshes" element={<RequireCapability cap="PROCUREMENT_ADMIN"><RefreshManagementPage /></RequireCapability>} />
        <Route path="/procurement/refresh" element={<RequireCapability cap="PROCUREMENT_WORKSPACE"><RefreshLauncherPage /></RequireCapability>} />
        <Route path="/procurement/workspace" element={<RequireCapability cap="PROCUREMENT_WORKSPACE"><PurchaseWorkspacePage /></RequireCapability>} />
        <Route path="/procurement/intelligence" element={<RequireCapability cap="PROCUREMENT_WORKSPACE"><ProductIntelligencePage /></RequireCapability>} />
        <Route path="/procurement/compare" element={<RequireCapability cap="PROCUREMENT_WORKSPACE"><RefreshComparePage /></RequireCapability>} />
        <Route path="/document-extraction/review" element={<RequireCapability cap="DOCUMENT_EXTRACTION"><DocumentExtractionReviewPage /></RequireCapability>} />
        <Route path="/document-extraction/review/:importId" element={<RequireCapability cap="DOCUMENT_EXTRACTION"><DocumentExtractionReviewPage /></RequireCapability>} />
        <Route path="/document-extraction/history" element={<RequireCapability cap="DOCUMENT_EXTRACTION"><DocumentExtractionHistoryPage /></RequireCapability>} />
        <Route path="/reports" element={<RequireCapability cap="REPORTS"><ReportsPage /></RequireCapability>} />
        <Route path="/pass-gen" element={<RequireCapability cap="PASS_GEN"><PassGenPage /></RequireCapability>} />
        <Route path="/legacy-order" element={<RequireCapability cap="LEGACY_ORDER"><LegacyOrderPage /></RequireCapability>} />
        <Route path="/settings" element={<RequireCapability cap="SETTINGS"><SettingsPage /></RequireCapability>} />
        <Route path="*" element={<RoleLanding />} />
      </Route>
    </>,
  ),
)
