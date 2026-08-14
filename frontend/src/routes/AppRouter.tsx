import { createBrowserRouter, createRoutesFromElements, Navigate, Route } from 'react-router-dom'
import { AppShell } from '../layouts/AppShell'
import { ProtectedRoute } from './ProtectedRoute'
import { RequireCapability } from './RequireCapability'
import { useAccess } from '../hooks/useAccess'
import PlatformOverviewPage from '../pages/PlatformOverviewPage'
import TenantWorkspacePage from '../pages/platform/TenantWorkspacePage'
import StoreWorkspacePage from '../pages/platform/StoreWorkspacePage'
import UserWorkspacePage from '../pages/platform/UserWorkspacePage'
import RoleWorkspacePage from '../pages/platform/RoleWorkspacePage'
import PlatformManagementPage from '../pages/platform/PlatformManagementPage'
import ModulesPage from '../pages/administration/ModulesPage'
import ModuleWorkspacePage from '../pages/administration/ModuleWorkspacePage'
import SyncLivePage from '../pages/sync/SyncLivePage'
import SyncSchedulesPage from '../pages/sync/SyncSchedulesPage'
import SyncConfigPage from '../pages/sync/SyncConfigPage'
import SyncMappingPage from '../pages/sync/SyncMappingPage'
import SyncStoreHealthPage from '../pages/sync/SyncStoreHealthPage'
import SyncHistoryPage from '../pages/sync/SyncHistoryPage'
import SyncAgentsPage from '../pages/sync/SyncAgentsPage'
import ProductMappingPage from '../pages/mapping/ProductMappingPage'
import StockAvailabilityPage from '../pages/stock/StockAvailabilityPage'
import StockCheckReportPage from '../pages/stock-check/StockCheckReportPage'
import LabelExporterPage from '../pages/label-export/LabelExporterPage'
import BoxWorkspacePage from '../pages/label-export/BoxWorkspacePage'
import NmwSalesReportPage from '../pages/nmw-sales/NmwSalesReportPage'
import StockIntegrityReportPage from '../pages/stock-integrity/StockIntegrityReportPage'
import PurchaseWorkspacePage from '../pages/procurement/PurchaseWorkspacePage'
import ProductIntelligencePage from '../pages/procurement/ProductIntelligencePage'
import RefreshLauncherPage from '../pages/procurement/RefreshLauncherPage'
import CycleManagementPage from '../pages/procurement/CycleManagementPage'
import RefreshManagementPage from '../pages/procurement/RefreshManagementPage'
import CycleRefreshConsolePage from '../pages/procurement/CycleRefreshConsolePage'
import RefreshComparePage from '../pages/procurement/RefreshComparePage'
import ShelfSortingPage from '../pages/procurement/ShelfSortingPage'
import ShelfCategoryTrainingPage from '../pages/procurement/ShelfCategoryTrainingPage'
import PharmacyReportsPage from '../pages/procurement/PharmacyReportsPage'
import SupplierStockDistributionPage from '../pages/procurement/SupplierStockDistributionPage'
import PermissionsPage from '../pages/administration/PermissionsPage'
import ReportsPage from '../pages/ReportsPage'
import TimeReportPage from '../pages/TimeReportPage'
import PassGenPage from '../pages/pass-gen/PassGenPage'
import LegacyOrderPage from '../pages/legacy-order/LegacyOrderPage'
import QtyCheckPage from '../pages/legacy-order/QtyCheckPage'
import SettingsPage from '../pages/SettingsPage'
import PlatformShellPreviewPage from '../pages/PlatformShellPreviewPage'
import DocumentExtractionReviewPage from '../pages/document-extraction/ReviewPage'
import DocumentExtractionHistoryPage from '../pages/document-extraction/HistoryPage'
import LoginPage from '../pages/LoginPage'

/** Sends the user to their role's landing page (Purchase Managers open directly
 *  into the Purchase Manager workspace). */
// eslint-disable-next-line react-refresh/only-export-components
function RoleLanding() {
  const { landingPath } = useAccess()
  return <Navigate to={landingPath} replace />
}

export const appRouter = createBrowserRouter(
  createRoutesFromElements(
    <>
      <Route path="/login" element={<LoginPage />} />
      {/* Desktop Platform shell preview — a separate top-level route (not
          nested under AppShell) so the new shell can be built and compared
          side-by-side without touching the existing app. Owner-directed: the
          sidebar (AppShell) is the one standard navigation pattern going
          forward, so this stays reachable for admins only (internal
          comparison/preview), not exposed to every logged-in user by URL. */}
      <Route
        path="/platform-shell-preview"
        element={
          <ProtectedRoute>
            <RequireCapability cap="ADMINISTRATION">
              <PlatformShellPreviewPage />
            </RequireCapability>
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
        <Route path="/platform/manage" element={<RequireCapability cap="PLATFORM"><PlatformManagementPage /></RequireCapability>} />
        <Route path="/platform/tenants" element={<Navigate to="/platform/manage" replace />} />
        <Route path="/platform/tenants/:tenantId" element={<RequireCapability cap="PLATFORM"><TenantWorkspacePage /></RequireCapability>} />
        <Route path="/platform/stores" element={<Navigate to="/platform/manage?tab=stores" replace />} />
        <Route path="/platform/stores/:storeId" element={<RequireCapability cap="PLATFORM"><StoreWorkspacePage /></RequireCapability>} />
        <Route path="/platform/users" element={<Navigate to="/platform/manage?tab=users" replace />} />
        <Route path="/platform/users/:userId" element={<RequireCapability cap="PLATFORM"><UserWorkspacePage /></RequireCapability>} />
        <Route path="/platform/roles" element={<Navigate to="/platform/manage?tab=roles" replace />} />
        <Route path="/platform/roles/:roleId" element={<RequireCapability cap="PLATFORM"><RoleWorkspacePage /></RequireCapability>} />
        <Route path="/administration/modules" element={<RequireCapability cap="ADMINISTRATION"><ModulesPage /></RequireCapability>} />
        <Route path="/administration/modules/:moduleId" element={<RequireCapability cap="ADMINISTRATION"><ModuleWorkspacePage /></RequireCapability>} />
        <Route path="/administration/permissions" element={<RequireCapability cap="ADMINISTRATION"><PermissionsPage /></RequireCapability>} />
        <Route path="/sync-administration" element={<Navigate to="/sync/live" replace />} />
        <Route path="/sync/dashboard" element={<Navigate to="/sync/live" replace />} />
        <Route path="/sync/tables" element={<Navigate to="/sync/live" replace />} />
        <Route path="/sync/live" element={<RequireCapability cap="SYNC"><SyncLivePage /></RequireCapability>} />
        <Route path="/sync/schedules" element={<RequireCapability cap="SYNC"><SyncSchedulesPage /></RequireCapability>} />
        <Route path="/sync/config" element={<RequireCapability cap="SYNC"><SyncConfigPage /></RequireCapability>} />
        <Route path="/sync/mapping" element={<RequireCapability cap="SYNC"><SyncMappingPage /></RequireCapability>} />
        <Route path="/sync/store-health" element={<RequireCapability cap="SYNC"><SyncStoreHealthPage /></RequireCapability>} />
        <Route path="/sync/history" element={<RequireCapability cap="SYNC"><SyncHistoryPage /></RequireCapability>} />
        <Route path="/sync/agents" element={<RequireCapability cap="SYNC"><SyncAgentsPage /></RequireCapability>} />
        <Route path="/product-mapping" element={<RequireCapability cap="PRODUCT_MAPPING"><ProductMappingPage /></RequireCapability>} />
        <Route path="/stock-availability" element={<RequireCapability cap="INVENTORY"><StockAvailabilityPage /></RequireCapability>} />
        <Route path="/stock-check-report" element={<RequireCapability cap="INVENTORY"><StockCheckReportPage /></RequireCapability>} />
        <Route path="/label-exporter" element={<RequireCapability cap="INVENTORY"><LabelExporterPage /></RequireCapability>} />
        <Route path="/label-exporter/box-workspace" element={<RequireCapability cap="INVENTORY"><BoxWorkspacePage /></RequireCapability>} />
        <Route path="/nmw-sales-report" element={<RequireCapability cap="INVENTORY"><NmwSalesReportPage /></RequireCapability>} />
        <Route path="/stock-integrity" element={<RequireCapability cap="INVENTORY"><StockIntegrityReportPage /></RequireCapability>} />
        <Route path="/procurement/console" element={<RequireCapability cap="PROCUREMENT_ADMIN"><CycleRefreshConsolePage /></RequireCapability>} />
        <Route path="/procurement/cycles" element={<RequireCapability cap="PROCUREMENT_ADMIN"><CycleManagementPage /></RequireCapability>} />
        <Route path="/procurement/refreshes" element={<RequireCapability cap="PROCUREMENT_ADMIN"><RefreshManagementPage /></RequireCapability>} />
        <Route path="/procurement/refresh" element={<RequireCapability cap="PROCUREMENT_WORKSPACE"><RefreshLauncherPage /></RequireCapability>} />
        <Route path="/procurement/workspace" element={<RequireCapability cap="PROCUREMENT_WORKSPACE"><PurchaseWorkspacePage /></RequireCapability>} />
        <Route path="/procurement/intelligence" element={<RequireCapability cap="PROCUREMENT_WORKSPACE"><ProductIntelligencePage /></RequireCapability>} />
        <Route path="/procurement/compare" element={<RequireCapability cap="PROCUREMENT_WORKSPACE"><RefreshComparePage /></RequireCapability>} />
        <Route path="/procurement/shelf-sort" element={<RequireCapability cap="PROCUREMENT_WORKSPACE"><ShelfSortingPage /></RequireCapability>} />
        <Route path="/procurement/shelf-categories" element={<RequireCapability cap="PROCUREMENT_WORKSPACE"><ShelfCategoryTrainingPage /></RequireCapability>} />
        <Route path="/procurement/reports" element={<RequireCapability cap="REPORTS"><PharmacyReportsPage /></RequireCapability>} />
        <Route path="/procurement/distribution" element={<RequireCapability cap="PROCUREMENT_ADMIN"><SupplierStockDistributionPage /></RequireCapability>} />
        <Route path="/document-extraction/review" element={<RequireCapability cap="DOCUMENT_EXTRACTION"><DocumentExtractionReviewPage /></RequireCapability>} />
        <Route path="/document-extraction/review/:importId" element={<RequireCapability cap="DOCUMENT_EXTRACTION"><DocumentExtractionReviewPage /></RequireCapability>} />
        <Route path="/document-extraction/history" element={<RequireCapability cap="DOCUMENT_EXTRACTION"><DocumentExtractionHistoryPage /></RequireCapability>} />
        <Route path="/reports" element={<RequireCapability cap="REPORTS"><ReportsPage /></RequireCapability>} />
        <Route path="/time-report" element={<RequireCapability cap="TIME_REPORT"><TimeReportPage /></RequireCapability>} />
        <Route path="/pass-gen" element={<RequireCapability cap="PASS_GEN"><PassGenPage /></RequireCapability>} />
        <Route path="/legacy-order" element={<RequireCapability cap="LEGACY_ORDER"><LegacyOrderPage /></RequireCapability>} />
        <Route path="/legacy-order/qty-check" element={<RequireCapability cap="LEGACY_ORDER"><QtyCheckPage /></RequireCapability>} />
        <Route path="/settings" element={<RequireCapability cap="SETTINGS"><SettingsPage /></RequireCapability>} />
        <Route path="*" element={<RoleLanding />} />
      </Route>
    </>,
  ),
)
