/// Named routes and their paths. Keeping names and paths together avoids
/// stringly-typed drift between the router and call sites.
class AppRoutes {
  AppRoutes._();

  static const String splash = 'splash';
  static const String splashPath = '/splash';

  static const String login = 'login';
  static const String loginPath = '/login';

  static const String storeSelection = 'store-selection';
  static const String storeSelectionPath = '/store-selection';

  static const String dashboard = 'dashboard';
  static const String dashboardPath = '/dashboard';

  // Store agent / sync system screens (Phase 2 + 3). Reachable once the session
  // is ready; no business modules live here.
  static const String syncStatus = 'sync-status';
  static const String syncStatusPath = '/sync-status';

  static const String deviceStatus = 'device-status';
  static const String deviceStatusPath = '/device-status';

  static const String agentSettings = 'agent-settings';
  static const String agentSettingsPath = '/agent-settings';

  static const String configurationStatus = 'configuration-status';
  static const String configurationStatusPath = '/configuration-status';
}
