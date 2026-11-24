// Source-to-destination map. Each loader is the existing frontend page.
// Paths are the Electron hash routes that already exist in navConfig.

export const WEB_PAGES = {
  'quick-stock': () => import('@web/pages/quick-stock/QuickStockPage.tsx'),
  'stock-check': () => import('@web/pages/stock-check/StockCheckReportPage.tsx'),
  'stock-integrity': () => import('@web/pages/stock-integrity/StockIntegrityReportPage.tsx'),
  'product-mapping': () => import('@web/pages/mapping/ProductMappingPage.tsx'),
  'warehouse-bill-export': () => import('@web/pages/nmw-sales/WarehouseBillExportPage.tsx'),
  'order-entry': () => import('@web/pages/legacy-order/OrderWorkspacePage.tsx'),
  'pm-order-entry': () => import('@web/pages/legacy-order/PmOrderEntryPage.tsx'),
  'order-gap-review': () => import('@web/pages/legacy-order/OrderGapReviewPage.tsx'),
  'previous-order-comparison': () => import('@web/pages/purchase/PreviousOrderComparisonPage.tsx'),
  'procurement-rules': () => import('@web/pages/procurement/ProcurementRulesPage.tsx'),
  'received-not-ordered': () => import('@web/pages/received-not-ordered/ReceivedNotOrderedPage.tsx'),
  'sales-reports': () => import('@web/pages/ReportsPage.tsx'),
  'expiry-report': () => import('@web/pages/expiry-report/ExpiryReportPage.tsx'),
  'expiry-stock': () => import('@web/pages/expiry-stock/ExpiryStockReportPage.tsx'),
  'sale-analysis': () => import('@web/pages/sale-analysis/SaleAnalysisPage.tsx'),
  'time-report': () => import('@web/pages/TimeReportPage.tsx'),
  'sync-live': () => import('@web/pages/sync/SyncLivePage.tsx'),
  'store-health': () => import('@web/pages/sync/StockClientMonitorPage.tsx'),
  'order-cache-monitor': () => import('@web/pages/sync/OrderCacheMonitorPage.tsx'),
  'device-control': () => import('@web/pages/sync/DeviceControllerPage.tsx'),
  'remote-terminal': () => import('@web/pages/sync/RemoteTerminalPage.tsx'),
  'platform-admin': () => import('@web/pages/platform/PlatformManagementPage.tsx'),
  'document-extraction': () => import('@web/pages/document-extraction/ReviewPage.tsx'),
  'document-history': () => import('@web/pages/document-extraction/HistoryPage.tsx'),
  'pass-gen': () => import('@web/pages/pass-gen/PassGenPage.tsx'),
  whatsapp: () => import('@web/pages/whatsapp/WhatsAppPage.tsx'),
  'sync-schedules': () => import('@web/pages/sync/SyncSchedulesPage.tsx'),
  'sync-config': () => import('@web/pages/sync/SyncConfigPage.tsx'),
  'sync-mapping': () => import('@web/pages/sync/SyncMappingPage.tsx'),
  'sync-agents': () => import('@web/pages/sync/SyncAgentsPage.tsx'),
  'sync-devices': () => import('@web/pages/sync/DeviceManagementPage.tsx'),
  'sync-mail': () => import('@web/pages/sync/SyncMailTransferPage.tsx'),
  'ho-routes': () => import('@web/pages/sync/HoRoutesPage.tsx'),
  'backend-update': () => import('@web/pages/sync/BackendUpdatePage.tsx'),
  permissions: () => import('@web/pages/administration/PermissionsPage.tsx'),
  modules: () => import('@web/pages/administration/ModulesPage.tsx'),
  'audit-logs': () => import('@web/pages/administration/AuditLogsPage.tsx'),
  'purchase-workspace': () => import('@web/pages/procurement/PurchaseWorkspacePage.tsx'),
  'product-intelligence': () => import('@web/pages/procurement/ProductIntelligencePage.tsx'),
  'refresh-compare': () => import('@web/pages/procurement/RefreshComparePage.tsx'),
  'shelf-sort': () => import('@web/pages/procurement/ShelfSortingPage.tsx'),
  'shelf-categories': () => import('@web/pages/procurement/ShelfCategoryTrainingPage.tsx'),
  'cycle-console': () => import('@web/pages/procurement/CycleRefreshConsolePage.tsx'),
  'supplier-distribution': () => import('@web/pages/procurement/SupplierStockDistributionPage.tsx'),
  'pharmacy-reports': () => import('@web/pages/procurement/PharmacyReportsPage.tsx'),
  'box-workspace': () => import('@web/pages/label-export/BoxWorkspacePage.tsx'),
  'non-moving-report': () => import('@web/pages/non-moving-report/NonMovingReportPage.tsx'),
  'live-queries': () => import('@web/pages/system/LiveQueriesPage.tsx'),
  'order-automation': () => import('@web/pages/system/OrderAutomationPage.tsx'),
};

export const WEB_PAGE_IDS = Object.keys(WEB_PAGES);

export function loadWebPage(pageId) {
  const load = WEB_PAGES[pageId];
  if (!load) return null;
  return load;
}
