import React from 'react';
import { HashRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ThemeProvider } from '../themes/ThemeContext.jsx';
import { AuthProvider } from '../contexts/AuthContext.jsx';
import { RequireAuth } from './RequireAuth.jsx';
import { AppShell } from '../layouts/AppShell.jsx';
import { DashboardPage } from '../modules/dashboard/DashboardPage.jsx';
import { SettingsPage } from '../modules/settings/SettingsPage.jsx';
import { StockEnquiryPage } from '../modules/stock-enquiry/StockEnquiryPage.jsx';
import { NonMovingStockPage } from '../modules/non-moving-stock/NonMovingStockPage.jsx';
import { LabelExportPage } from '../modules/label-export/LabelExportPage.jsx';
import { LegacyOrderPage } from '../modules/legacy-order/LegacyOrderPage.jsx';
import { RateAnalysisPage } from '../modules/rate-analysis/RateAnalysisPage.jsx';
import { AiIntelligencePage } from '../modules/ai-intelligence/AiIntelligencePage.jsx';
import { SupplierStockPage } from '../modules/supplier-stock/SupplierStockPage.jsx';
import { SupplierStockList } from '../modules/supplier-stock/SupplierStockList.jsx';
import { ProcurementWorkspacePage } from '../modules/procurement-workspace/ProcurementWorkspacePage.jsx';
import { WorkspaceModulePage } from '../modules/workspace/WorkspaceModulePage.jsx';
import { WebModuleHost } from '../bridge/WebModuleHost.jsx';
import MaintenanceScreen from '../components/MaintenanceScreen.jsx';
import { resolveApiBaseUrl } from '../services/settingsStore.js';
import 'bootstrap/dist/css/bootstrap.min.css';
import 'bootstrap-icons/font/bootstrap-icons.css';
import '../themes/tokens.css';
import '../layouts/shell.css';
import './login.css';
import '../modules/stock-enquiry/stockEnquiry.css';
import '../modules/ai-intelligence/aiIntelligence.css';
import '../modules/supplier-stock/supplierStock.css';
import '../modules/workspace/workspace.css';

function workspace(moduleId) {
  return <WorkspaceModulePage key={moduleId} moduleId={moduleId} />;
}

function web(pageId) {
  return <WebModuleHost key={pageId} pageId={pageId} />;
}

export function App() {
  return (
    <ThemeProvider>
      <MaintenanceScreen getBaseUrl={resolveApiBaseUrl} />
      <AuthProvider>
        <HashRouter>
          <RequireAuth>
            <Routes>
              <Route path="/" element={<AppShell />}>
                <Route index element={<Navigate to="/dashboard" replace />} />
                <Route path="dashboard" element={<DashboardPage />} />
                <Route path="stock-enquiry" element={<StockEnquiryPage />} />
                <Route path="settings" element={<SettingsPage />} />
                <Route path="inventory/network-stock" element={workspace('network-stock')} />
                <Route path="inventory/non-moving" element={<NonMovingStockPage />} />
                <Route path="inventory/non-moving-report" element={web('non-moving-report')} />
                <Route path="inventory/stock-check" element={web('stock-check')} />
                <Route path="inventory/stock-integrity" element={web('stock-integrity')} />
                <Route path="inventory/product-mapping" element={web('product-mapping')} />
                <Route path="inventory/label-export" element={<LabelExportPage />} />
                <Route path="inventory/box-workspace" element={web('box-workspace')} />
                <Route path="label-exporter/box-workspace" element={web('box-workspace')} />
                <Route path="inventory/warehouse-bill-export" element={web('warehouse-bill-export')} />
                <Route path="supplier-stock" element={<SupplierStockPage />} />
                <Route path="supplier-stock-list" element={<SupplierStockList />} />
                <Route path="quick-stock" element={web('quick-stock')} />
                <Route path="supplier-intelligence/rate-analysis" element={<RateAnalysisPage />} />
                <Route path="procurement" element={<ProcurementWorkspacePage />} />
                <Route path="procurement/purchase" element={web('purchase-workspace')} />
                <Route path="procurement/intelligence" element={web('product-intelligence')} />
                <Route path="procurement/compare" element={web('refresh-compare')} />
                <Route path="procurement/shelf-sort" element={web('shelf-sort')} />
                <Route path="procurement/shelf-categories" element={web('shelf-categories')} />
                <Route path="procurement/console" element={web('cycle-console')} />
                <Route path="procurement/distribution" element={web('supplier-distribution')} />
                <Route path="procurement/reports" element={web('pharmacy-reports')} />
                <Route path="procurement/order-workspace" element={web('order-entry')} />
                <Route path="procurement/order-entry" element={web('order-entry')} />
                <Route path="procurement/order-entry-submit" element={web('pm-order-entry')} />
                <Route path="procurement/order-gap-review" element={web('order-gap-review')} />
                <Route path="procurement/previous-order-comparison" element={web('previous-order-comparison')} />
                <Route path="legacy-order" element={<LegacyOrderPage />} />
                <Route path="legacy-order/workspace" element={web('order-entry')} />
                <Route path="procurement/legacy-order" element={<LegacyOrderPage />} />
                <Route path="procurement/rules" element={web('procurement-rules')} />
                <Route path="procurement/received-not-ordered" element={web('received-not-ordered')} />
                <Route path="sales-reports" element={web('sales-reports')} />
                <Route path="sales-reports/expiry" element={web('expiry-report')} />
                <Route path="sales-reports/expiry-stock" element={web('expiry-stock')} />
                <Route path="sales-reports/sale-analysis" element={web('sale-analysis')} />
                <Route path="ai-intelligence" element={<AiIntelligencePage />} />
                <Route path="tools/time-report" element={web('time-report')} />
                <Route path="sync/live" element={web('sync-live')} />
                <Route path="sync/live-queries" element={web('live-queries')} />
                <Route path="administration/order-automation" element={web('order-automation')} />
                <Route path="sync/history" element={workspace('sync-history')} />
                <Route path="sync/schedules" element={web('sync-schedules')} />
                <Route path="sync/config" element={web('sync-config')} />
                <Route path="sync/mapping" element={web('sync-mapping')} />
                <Route path="sync/agents" element={web('sync-agents')} />
                <Route path="sync/devices" element={web('sync-devices')} />
                <Route path="sync/mail-transfer" element={web('sync-mail')} />
                <Route path="sync/ho-routes" element={web('ho-routes')} />
                <Route path="sync/backend-update" element={web('backend-update')} />
                <Route path="sync/store-health" element={web('store-health')} />
                <Route path="sync/order-cache" element={web('order-cache-monitor')} />
                <Route path="sync/device-control" element={web('device-control')} />
                <Route path="sync/terminal" element={web('remote-terminal')} />
                <Route path="administration" element={workspace('administration')} />
                <Route path="administration/permissions" element={web('permissions')} />
                <Route path="administration/modules" element={web('modules')} />
                <Route path="administration/audit-logs" element={web('audit-logs')} />
                <Route path="administration/platform" element={web('platform-admin')} />
                <Route path="platform/manage" element={web('platform-admin')} />
                <Route path="tools/document-extraction" element={web('document-extraction')} />
                <Route path="document-extraction/review" element={web('document-extraction')} />
                <Route path="document-extraction/review/:importId" element={web('document-extraction')} />
                <Route path="document-extraction/history" element={web('document-history')} />
                <Route path="tools/pass-gen" element={web('pass-gen')} />
                <Route path="tools/whatsapp" element={web('whatsapp')} />
              </Route>
            </Routes>
          </RequireAuth>
        </HashRouter>
      </AuthProvider>
    </ThemeProvider>
  );
}
