import 'package:flutter/widgets.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:nexora_mobile/core/navigation/app_shell.dart';
import 'package:nexora_mobile/core/router/app_routes.dart';
import 'package:nexora_mobile/features/agent/presentation/agent_settings_screen.dart';
import 'package:nexora_mobile/features/agent/presentation/configuration_status_screen.dart';
import 'package:nexora_mobile/features/agent/presentation/device_status_screen.dart';
import 'package:nexora_mobile/features/auth/application/auth_controller.dart';
import 'package:nexora_mobile/features/auth/application/auth_state.dart';
import 'package:nexora_mobile/features/auth/presentation/login_screen.dart';
import 'package:nexora_mobile/features/dashboard/presentation/dashboard_screen.dart';
import 'package:nexora_mobile/features/document_extraction/presentation/camera_capture_screen.dart';
import 'package:nexora_mobile/features/document_extraction/presentation/capture_queue_screen.dart';
import 'package:nexora_mobile/features/document_extraction/presentation/capture_screen.dart';
import 'package:nexora_mobile/features/document_extraction/presentation/document_review_screen.dart';
import 'package:nexora_mobile/features/master_data/presentation/suppliers_screen.dart';
import 'package:nexora_mobile/features/pass_gen/presentation/pass_gen_screen.dart';
import 'package:nexora_mobile/features/procurement/presentation/cycle_console_screen.dart';
import 'package:nexora_mobile/features/procurement/presentation/legacy_order_console_screen.dart';
import 'package:nexora_mobile/features/procurement/presentation/procurement_hub_screen.dart';
import 'package:nexora_mobile/features/reports/presentation/reports_catalog_screen.dart';
import 'package:nexora_mobile/features/time_report/presentation/time_report_screen.dart';
import 'package:nexora_mobile/features/settings/presentation/more_screen.dart';
import 'package:nexora_mobile/features/settings/presentation/pending_changes_screen.dart';
import 'package:nexora_mobile/features/settings/presentation/settings_screen.dart';
import 'package:nexora_mobile/features/store_selection/presentation/store_selection_screen.dart';
import 'package:nexora_mobile/features/sync/presentation/sync_live_screen.dart';
import 'package:nexora_mobile/features/sync/presentation/sync_status_screen.dart';
import 'package:nexora_mobile/shared/presentation/splash_screen.dart';

/// Bridges Riverpod's [AuthState] into a [Listenable] GoRouter can refresh on,
/// and centralises the redirect (guard) logic for the whole app.
class RouterNotifier extends ChangeNotifier {
  RouterNotifier(this._ref) {
    _ref.listen<AuthState>(
        authControllerProvider, (_, __) => notifyListeners());
  }

  final Ref _ref;

  String? redirect(BuildContext context, GoRouterState state) {
    final auth = _ref.read(authControllerProvider);
    final location = state.matchedLocation;

    // 1) Still resolving a stored session → hold on the splash screen.
    if (auth.status == AuthStatus.unknown) {
      return location == AppRoutes.splashPath ? null : AppRoutes.splashPath;
    }

    final loggingIn = location == AppRoutes.loginPath;
    final onSplash = location == AppRoutes.splashPath;

    // 2) Not authenticated → force login.
    if (auth.status == AuthStatus.unauthenticated) {
      return loggingIn ? null : AppRoutes.loginPath;
    }

    // 3) Authenticated but no store chosen → store selection.
    if (!auth.hasStore) {
      return location == AppRoutes.storeSelectionPath
          ? null
          : AppRoutes.storeSelectionPath;
    }

    // 4) Fully ready → keep out of the auth/splash funnel.
    if (loggingIn || onSplash || location == AppRoutes.storeSelectionPath) {
      return AppRoutes.homePath;
    }
    return null;
  }
}

final routerNotifierProvider = ChangeNotifierProvider<RouterNotifier>(
  RouterNotifier.new,
);

/// Root navigator key, so the pre-session screens render above the tab shell
/// rather than inside it.
final _rootNavigatorKey = GlobalKey<NavigatorState>();

final routerProvider = Provider<GoRouter>((ref) {
  final notifier = ref.watch(routerNotifierProvider);
  return GoRouter(
    navigatorKey: _rootNavigatorKey,
    initialLocation: AppRoutes.splashPath,
    refreshListenable: notifier,
    redirect: notifier.redirect,
    routes: [
      // --- Pre-session funnel: no tab bar --------------------------------------
      GoRoute(
        path: AppRoutes.splashPath,
        name: AppRoutes.splash,
        builder: (_, __) => const SplashScreen(),
      ),
      GoRoute(
        path: AppRoutes.loginPath,
        name: AppRoutes.login,
        builder: (_, __) => const LoginScreen(),
      ),
      GoRoute(
        path: AppRoutes.storeSelectionPath,
        name: AppRoutes.storeSelection,
        builder: (_, __) => const StoreSelectionScreen(),
      ),

      // --- Tab shell -----------------------------------------------------------
      // Branch order MUST match AppSection's declaration order: AppShell maps a
      // section to its branch by enum index.
      StatefulShellRoute.indexedStack(
        builder: (_, __, navigationShell) =>
            AppShell(navigationShell: navigationShell),
        branches: [
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: AppRoutes.homePath,
                name: AppRoutes.home,
                builder: (_, __) => const DashboardScreen(),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: AppRoutes.capturePath,
                name: AppRoutes.capture,
                builder: (_, __) => const CaptureScreen(),
                routes: [
                  // The one screen that deliberately escapes the shell: a
                  // viewfinder needs the full display, and a tab bar under it
                  // is an invitation to walk away mid-document. Pushing onto
                  // the root navigator hides the bar; popping returns to the
                  // Capture tab as usual.
                  GoRoute(
                    path: AppRoutes.cameraCapturePath,
                    name: AppRoutes.cameraCapture,
                    parentNavigatorKey: _rootNavigatorKey,
                    builder: (_, __) => const CameraCaptureScreen(),
                  ),
                  // The queue, by contrast, stays inside the shell: it is a
                  // list you dip into and tab away from.
                  GoRoute(
                    path: AppRoutes.captureQueuePath,
                    name: AppRoutes.captureQueue,
                    builder: (_, __) => const CaptureQueueScreen(),
                  ),
                  GoRoute(
                    path: AppRoutes.documentReviewPath,
                    name: AppRoutes.documentReview,
                    builder: (_, state) => DocumentReviewScreen(
                      // A path that cannot be parsed is a bad link, not a
                      // crash: import 0 loads nothing and shows the error
                      // surface the screen already has.
                      importId: int.tryParse(
                              state.pathParameters['importId'] ?? '') ??
                          0,
                      batchId: int.tryParse(
                          state.uri.queryParameters['batch'] ?? ''),
                    ),
                  ),
                ],
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: AppRoutes.procurePath,
                name: AppRoutes.procure,
                builder: (_, __) => const ProcurementHubScreen(),
                routes: [
                  GoRoute(
                    path: AppRoutes.cycleConsolePath,
                    name: AppRoutes.cycleConsole,
                    builder: (_, __) => const CycleConsoleScreen(),
                  ),
                  GoRoute(
                    path: AppRoutes.legacyOrderConsolePath,
                    name: AppRoutes.legacyOrderConsole,
                    builder: (_, __) => const LegacyOrderConsoleScreen(),
                  ),
                ],
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: AppRoutes.syncPath,
                name: AppRoutes.sync,
                builder: (_, __) => const SyncStatusScreen(),
                routes: [
                  GoRoute(
                    path: AppRoutes.syncLivePath,
                    name: AppRoutes.syncLive,
                    builder: (_, __) => const SyncLiveScreen(),
                  ),
                ],
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: AppRoutes.morePath,
                name: AppRoutes.more,
                builder: (_, __) => const MoreScreen(),
                // Nested so the tab bar stays visible and each screen joins the
                // More tab's own back stack.
                routes: [
                  GoRoute(
                    path: AppRoutes.reportsPath,
                    name: AppRoutes.reports,
                    builder: (_, __) => const ReportsCatalogScreen(),
                  ),
                  GoRoute(
                    path: AppRoutes.suppliersPath,
                    name: AppRoutes.suppliers,
                    builder: (_, __) => const SuppliersScreen(),
                  ),
                  GoRoute(
                    path: AppRoutes.timeReportPath,
                    name: AppRoutes.timeReport,
                    builder: (_, __) => const TimeReportScreen(),
                  ),
                  GoRoute(
                    path: AppRoutes.passGenPath,
                    name: AppRoutes.passGen,
                    builder: (_, __) => const PassGenScreen(),
                  ),
                  GoRoute(
                    path: AppRoutes.deviceStatusPath,
                    name: AppRoutes.deviceStatus,
                    builder: (_, __) => const DeviceStatusScreen(),
                  ),
                  GoRoute(
                    path: AppRoutes.configurationStatusPath,
                    name: AppRoutes.configurationStatus,
                    builder: (_, __) => const ConfigurationStatusScreen(),
                  ),
                  GoRoute(
                    path: AppRoutes.agentSettingsPath,
                    name: AppRoutes.agentSettings,
                    builder: (_, __) => const AgentSettingsScreen(),
                  ),
                  GoRoute(
                    path: AppRoutes.settingsPath,
                    name: AppRoutes.settings,
                    builder: (_, __) => const SettingsScreen(),
                  ),
                  GoRoute(
                    path: AppRoutes.pendingChangesPath,
                    name: AppRoutes.pendingChanges,
                    builder: (_, __) => const PendingChangesScreen(),
                  ),
                ],
              ),
            ],
          ),
        ],
      ),
    ],
  );
});
