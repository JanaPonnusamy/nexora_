/// Named routes and their paths. Keeping names and paths together avoids
/// stringly-typed drift between the router and call sites.
///
/// Layout mirrors the navigation model: five persistent tabs, each the root of
/// its own branch, with feature screens pushed on top of the owning tab so the
/// bar stays visible and each tab keeps its own history.
class AppRoutes {
  AppRoutes._();

  // --- Pre-session funnel (no tab bar) ---------------------------------------

  static const String splash = 'splash';
  static const String splashPath = '/splash';

  static const String login = 'login';
  static const String loginPath = '/login';

  static const String storeSelection = 'store-selection';
  static const String storeSelectionPath = '/store-selection';

  // --- Tab roots -------------------------------------------------------------

  static const String home = 'home';
  static const String homePath = '/home';

  static const String capture = 'capture';
  static const String capturePath = '/capture';

  static const String procure = 'procure';
  static const String procurePath = '/procure';

  static const String sync = 'sync';
  static const String syncPath = '/sync';

  static const String more = 'more';
  static const String morePath = '/more';

  // --- Screens nested under the Capture tab ----------------------------------

  static const String cameraCapture = 'camera-capture';
  static const String cameraCapturePath = 'camera';

  static const String captureQueue = 'capture-queue';
  static const String captureQueuePath = 'queue';

  /// Review of one extracted document. The import id is in the path so the
  /// screen can be reached directly (from a notification, later); the local
  /// batch it came from rides along as an optional `batch` query parameter,
  /// because it only exists for documents captured on this device.
  static const String documentReview = 'document-review';
  static const String documentReviewPath = 'review/:importId';

  static const String cameraCaptureFullPath = '$capturePath/$cameraCapturePath';
  static const String captureQueueFullPath = '$capturePath/$captureQueuePath';

  static String documentReviewLocation(int importId, {int? batchId}) =>
      '$capturePath/review/$importId${batchId == null ? '' : '?batch=$batchId'}';

  // --- Screens nested under the Procure tab ----------------------------------

  static const String cycleConsole = 'cycle-console';
  static const String cycleConsolePath = 'cycles';

  static const String purchaseWorkspace = 'purchase-workspace';
  static const String purchaseWorkspacePath = 'purchase-workspace';

  static const String refreshCompare = 'refresh-compare';
  static const String refreshComparePath = 'refresh-compare';

  static const String stockDistribution = 'stock-distribution';
  static const String stockDistributionPath = 'stock-distribution';

  static const String procurementConflicts = 'procurement-conflicts';
  static const String procurementConflictsPath = 'conflicts';

  static const String suppliers = 'suppliers';
  static const String suppliersPath = 'suppliers';

  static const String legacyOrderConsole = 'legacy-order-console';
  static const String legacyOrderConsolePath = 'legacy-order';

  static const String cycleConsoleFullPath = '$procurePath/$cycleConsolePath';
  static const String purchaseWorkspaceFullPath =
      '$procurePath/$purchaseWorkspacePath';
  static const String refreshCompareFullPath =
      '$procurePath/$refreshComparePath';
  static const String stockDistributionFullPath =
      '$procurePath/$stockDistributionPath';
  static const String procurementConflictsFullPath =
      '$procurePath/$procurementConflictsPath';
  static const String suppliersFullPath = '$procurePath/$suppliersPath';
  static const String legacyOrderConsoleFullPath =
      '$procurePath/$legacyOrderConsolePath';

  // --- Screens nested under the Sync tab -------------------------------------

  static const String syncLive = 'sync-live';
  static const String syncLivePath = 'live';

  static const String syncLiveFullPath = '$syncPath/$syncLivePath';

  // --- Screens nested under the More tab -------------------------------------
  // Store-agent and device screens. These are diagnostics rather than business
  // modules, so they live behind More instead of claiming a tab of their own.

  static const String reports = 'reports';
  static const String reportsPath = 'reports';

  static const String timeReport = 'time-report';
  static const String timeReportPath = 'time-report';

  static const String passGen = 'pass-gen';
  static const String passGenPath = 'pass-gen';

  static const String deviceStatus = 'device-status';
  static const String deviceStatusPath = 'device-status';

  static const String agentSettings = 'agent-settings';
  static const String agentSettingsPath = 'agent-settings';

  static const String configurationStatus = 'configuration-status';
  static const String configurationStatusPath = 'configuration-status';

  static const String settings = 'settings';
  static const String settingsPath = 'settings';

  static const String pendingChanges = 'pending-changes';
  static const String pendingChangesPath = 'pending-changes';

  /// Absolute paths for the More sub-routes, for callers that navigate by path.
  static const String reportsFullPath = '$morePath/$reportsPath';
  static const String passGenFullPath = '$morePath/$passGenPath';
  static const String timeReportFullPath = '$morePath/$timeReportPath';
  static const String deviceStatusFullPath = '$morePath/$deviceStatusPath';
  static const String agentSettingsFullPath = '$morePath/$agentSettingsPath';
  static const String configurationStatusFullPath =
      '$morePath/$configurationStatusPath';
  static const String settingsFullPath = '$morePath/$settingsPath';
  static const String pendingChangesFullPath = '$morePath/$pendingChangesPath';
}
