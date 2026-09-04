import { lazy } from 'react'
import { createBrowserRouter, createRoutesFromElements, Navigate, Route } from 'react-router-dom'
import { AppShell } from '../layouts/AppShell'
import { ProtectedRoute } from './ProtectedRoute'
import { RequireCapability } from './RequireCapability'
import { useAccess } from '../hooks/useAccess'

const PlatformOverviewPage = lazy(() => import('../pages/PlatformOverviewPage'))
const TenantWorkspacePage = lazy(() => import('../pages/platform/TenantWorkspacePage'))
const StoreWorkspacePage = lazy(() => import('../pages/platform/StoreWorkspacePage'))
const UserWorkspacePage = lazy(() => import('../pages/platform/UserWorkspacePage'))
const RoleWorkspacePage = lazy(() => import('../pages/platform/RoleWorkspacePage'))
const PlatformManagementPage = lazy(() => import('../pages/platform/PlatformManagementPage'))
const ModulesPage = lazy(() => import('../pages/administration/ModulesPage'))
const ModuleWorkspacePage = lazy(() => import('../pages/administration/ModuleWorkspacePage'))
const SyncLivePage = lazy(() => import('../pages/sync/SyncLivePage'))
const SyncSchedulesPage = lazy(() => import('../pages/sync/SyncSchedulesPage'))
const SyncConfigPage = lazy(() => import('../pages/sync/SyncConfigPage'))
const SyncMappingPage = lazy(() => import('../pages/sync/SyncMappingPage'))
const SyncAgentsPage = lazy(() => import('../pages/sync/SyncAgentsPage'))
const ProductMappingPage = lazy(() => import('../pages/mapping/ProductMappingPage'))
const StockAvailabilityPage = lazy(() => import('../pages/stock/StockAvailabilityPage'))
const StockCheckReportPage = lazy(() => import('../pages/stock-check/StockCheckReportPage'))
const LabelExporterPage = lazy(() => import('../pages/label-export/LabelExporterPage'))
const BoxWorkspacePage = lazy(() => import('../pages/label-export/BoxWorkspacePage'))
const NmwSalesReportPage = lazy(() => import('../pages/nmw-sales/NmwSalesReportPage'))
const StockIntegrityReportPage = lazy(() => import('../pages/stock-integrity/StockIntegrityReportPage'))
const PurchaseWorkspacePage = lazy(() => import('../pages/procurement/PurchaseWorkspacePage'))
const ProductIntelligencePage = lazy(() => import('../pages/procurement/ProductIntelligencePage'))
const RefreshLauncherPage = lazy(() => import('../pages/procurement/RefreshLauncherPage'))
const CycleManagementPage = lazy(() => import('../pages/procurement/CycleManagementPage'))
const RefreshManagementPage = lazy(() => import('../pages/procurement/RefreshManagementPage'))
const CycleRefreshConsolePage = lazy(() => import('../pages/procurement/CycleRefreshConsolePage'))
const RefreshComparePage = lazy(() => import('../pages/procurement/RefreshComparePage'))
const ShelfSortingPage = lazy(() => import('../pages/procurement/ShelfSortingPage'))
const ShelfCategoryTrainingPage = lazy(() => import('../pages/procurement/ShelfCategoryTrainingPage'))
const PharmacyReportsPage = lazy(() => import('../pages/procurement/PharmacyReportsPage'))
const SupplierStockDistributionPage = lazy(() => import('../pages/procurement/SupplierStockDistributionPage'))
const PermissionsPage = lazy(() => import('../pages/administration/PermissionsPage'))
const AuditLogsPage = lazy(() => import('../pages/administration/AuditLogsPage'))
const ReportsPage = lazy(() => import('../pages/ReportsPage'))
const ExpiryReportPage = lazy(() => import('../pages/expiry-report/ExpiryReportPage'))
const ExpiryStockReportPage = lazy(() => import('../pages/expiry-stock/ExpiryStockReportPage'))
const NonMovingReportPage = lazy(() => import('../pages/non-moving-report/NonMovingReportPage'))
const SaleAnalysisPage = lazy(() => import('../pages/sale-analysis/SaleAnalysisPage'))
const TimeReportPage = lazy(() => import('../pages/TimeReportPage'))
const PassGenPage = lazy(() => import('../pages/pass-gen/PassGenPage'))
const LegacyOrderPage = lazy(() => import('../pages/legacy-order/LegacyOrderPage'))
const OrderWorkspacePage = lazy(() => import('../pages/legacy-order/OrderWorkspacePage'))
const WhatsAppPage = lazy(() => import('../pages/whatsapp/WhatsAppPage'))
const SettingsPage = lazy(() => import('../pages/SettingsPage'))
const PlatformShellPreviewPage = lazy(() => import('../pages/PlatformShellPreviewPage'))
const DocumentExtractionReviewPage = lazy(() => import('../pages/document-extraction/ReviewPage'))
const DocumentExtractionHistoryPage = lazy(() => import('../pages/document-extraction/HistoryPage'))
const LoginPage = lazy(() => import('../pages/LoginPage'))

/** Sends the user to their role's landing page (Purchase Managers open directly
 *  into the Purchase Manager workspace). */
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
        <Route path="/administration/audit-logs" element={<RequireCapability cap="ADMINISTRATION"><AuditLogsPage /></RequireCapability>} />
        <Route path="/sync-administration" element={<Navigate to="/sync/live" replace />} />
        <Route path="/sync/dashboard" element={<Navigate to="/sync/live" replace />} />
        <Route path="/sync/tables" element={<Navigate to="/sync/live" replace />} />
        <Route path="/sync/live" element={<RequireCapability cap="SYNC"><SyncLivePage /></RequireCapability>} />
        <Route path="/sync/schedules" element={<RequireCapability cap="SYNC"><SyncSchedulesPage /></RequireCapability>} />
        <Route path="/sync/config" element={<RequireCapability cap="SYNC"><SyncConfigPage /></RequireCapability>} />
        <Route path="/sync/mapping" element={<RequireCapability cap="SYNC"><SyncMappingPage /></RequireCapability>} />
        <Route path="/sync/store-health" element={<Navigate to="/sync/live" replace />} />
        <Route path="/sync/history" element={<Navigate to="/sync/live" replace />} />
        <Route path="/sync/agents" element={<RequireCapability cap="SYNC"><SyncAgentsPage /></RequireCapability>} />
        <Route path="/product-mapping" element={<RequireCapability cap="PRODUCT_MAPPING"><ProductMappingPage /></RequireCapability>} />
        <Route path="/stock-availability" element={<RequireCapability cap="INVENTORY"><StockAvailabilityPage /></RequireCapability>} />
        <Route path="/stock-check-report" element={<RequireCapability cap="INVENTORY"><StockCheckReportPage /></RequireCapability>} />
        <Route path="/label-exporter" element={<RequireCapability cap="INVENTORY"><LabelExporterPage /></RequireCapability>} />
        <Route path="/label-exporter/box-workspace" element={<RequireCapability cap="INVENTORY"><BoxWorkspacePage /></RequireCapability>} />
        <Route path="/label-exporter/review" element={<Navigate to="/label-exporter" replace />} />
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
        <Route path="/expiry-report" element={<RequireCapability cap="REPORTS"><ExpiryReportPage /></RequireCapability>} />
        <Route path="/expiry-stock" element={<RequireCapability cap="REPORTS"><ExpiryStockReportPage /></RequireCapability>} />
        <Route path="/non-moving-report" element={<RequireCapability cap="INVENTORY"><NonMovingReportPage /></RequireCapability>} />
        <Route path="/sale-analysis" element={<RequireCapability cap="INVENTORY"><SaleAnalysisPage /></RequireCapability>} />
        <Route path="/time-report" element={<RequireCapability cap="TIME_REPORT"><TimeReportPage /></RequireCapability>} />
        <Route path="/pass-gen" element={<RequireCapability cap="PASS_GEN"><PassGenPage /></RequireCapability>} />
        <Route path="/legacy-order" element={<RequireCapability cap="LEGACY_ORDER"><LegacyOrderPage /></RequireCapability>} />
        <Route path="/legacy-order/qty-check" element={<Navigate to="/legacy-order/workspace" replace />} />
        <Route path="/legacy-order/workspace" element={<RequireCapability cap="LEGACY_ORDER"><OrderWorkspacePage /></RequireCapability>} />
        <Route path="/whatsapp" element={<RequireCapability cap="SETTINGS"><WhatsAppPage /></RequireCapability>} />
        <Route path="/settings" element={<RequireCapability cap="SETTINGS"><SettingsPage /></RequireCapability>} />
        <Route path="*" element={<RoleLanding />} />
      </Route>
    </>,
  ),
)
