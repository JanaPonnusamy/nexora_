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
  static String storesByTenant(String tenantId) =>
      '/api/stores/tenant/$tenantId';
  static String store(String storeId) => '/api/stores/$storeId';

  // Master data (Phase 4). Only Suppliers has a real, mobile-consumable read
  // endpoint today; see docs/API_CONTRACT.md for the gaps on the others.
  //
  // The admin-tier route it used to call, kept for reference: a login whose
  // roles are all purchase-manager and/or salesman is 403'd there, so those
  // users saw an empty supplier list. Suppliers now come from the BFF route
  // below, which resolves scope from the token instead of gating on role.
  static const String adminSuppliersList =
      '/api/supplier-stock-analysis/suppliers';

  // Sync administration (read-only). Same endpoint the HO web console's Sync
  // Control Center uses; not tenant-scoped server-side, so the client only
  // surfaces it to platform users. See docs/API_CONTRACT.md.
  static const String syncControlCenter = '/api/sync/control-center';

  /// In-flight executions across the network (`runtime_router.py`). Returns a
  /// bare JSON array, not an object.
  static const String syncLive = '/api/sync/live';

  /// Bulk PAUSE / STOP of running executions.
  static const String syncControl = '/api/sync/control';

  /// Queues a sync task for a store; the store agent picks it up when it polls.
  static const String syncTaskCreate = '/api/sync/tasks/create';

  /// Completed and failed executions.
  static const String syncHistory = '/api/sync/history';

  // --- Mobile BFF (/api/mobile/v1) -------------------------------------------
  // Mobile-shaped endpoints added for this client. Unlike the routes above,
  // these resolve tenant/store from the JWT rather than query parameters.

  /// Public. Version/compatibility probe, answered before any credential.
  static const String mobileHandshake = '/api/mobile/v1/handshake';

  /// Public. Like /api/auth/login but also returns a rotating refresh token.
  static const String mobileLogin = '/api/mobile/v1/auth/login';

  /// Public — authenticated by the refresh token itself, since the bearer
  /// token has expired by the time this is called.
  static const String mobileRefresh = '/api/mobile/v1/auth/refresh';

  static const String mobileLogout = '/api/mobile/v1/auth/logout';
  static const String mobileDevices = '/api/mobile/v1/auth/devices';

  /// Single aggregate backing the Home tab.
  static const String mobileDashboard = '/api/mobile/v1/dashboard';

  /// Supplier list for the Supplier screen. Same `{suppliers: [...]}` payload
  /// as the admin-tier route, without the role gate that locks out the field
  /// roles this app is for.
  static const String mobileSuppliers = '/api/mobile/v1/suppliers';
}
