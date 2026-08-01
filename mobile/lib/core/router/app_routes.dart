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
}
