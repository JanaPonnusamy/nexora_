/// Central registry of backend endpoint paths consumed by the mobile app.
///
/// These MUST match the FastAPI routes exactly. The backend is the single
/// source of truth; if a path here drifts from the server it is a bug here,
/// not there. Only Phase 1 (auth + stores + health) endpoints are listed.
class ApiEndpoints {
  ApiEndpoints._();

  // Health / connectivity probe (no auth).
  static const String health = '/health';

  // Authentication.
  static const String login = '/api/auth/login';
  static const String me = '/api/auth/me';

  // Stores.
  static const String stores = '/api/stores';
  static String storesByTenant(String tenantId) => '/api/stores/tenant/$tenantId';
  static String store(String storeId) => '/api/stores/$storeId';

  // Master data (Phase 4). Only Suppliers has a real, mobile-consumable read
  // endpoint today; see docs/API_CONTRACT.md for the gaps on the others.
  static const String suppliersList = '/api/supplier-stock-analysis/suppliers';
}
