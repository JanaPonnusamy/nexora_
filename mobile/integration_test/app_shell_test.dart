import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:integration_test/integration_test.dart';

import 'package:nexora_mobile/core/agent/agent_state.dart';
import 'package:nexora_mobile/core/di/agent_providers.dart';
import 'package:nexora_mobile/core/navigation/app_section.dart';
import 'package:nexora_mobile/core/navigation/app_shell.dart';
import 'package:nexora_mobile/core/router/app_routes.dart';
import 'package:nexora_mobile/core/theme/app_theme.dart';
import 'package:nexora_mobile/features/auth/application/auth_controller.dart';
import 'package:nexora_mobile/features/auth/application/auth_state.dart';
import 'package:nexora_mobile/features/auth/data/models/app_user.dart';
import 'package:nexora_mobile/features/dashboard/presentation/dashboard_screen.dart';
import 'package:nexora_mobile/features/document_extraction/presentation/capture_queue_screen.dart';
import 'package:nexora_mobile/features/document_extraction/presentation/capture_screen.dart';
import 'package:nexora_mobile/features/procurement/presentation/procurement_hub_screen.dart';
import 'package:nexora_mobile/features/settings/presentation/more_screen.dart';

/// Auth controller pinned to a ready session, so the shell is reachable without
/// a live backend.
class _ReadyAuthController extends AuthController {
  @override
  AuthState build() => const AuthState(
        status: AuthStatus.authenticated,
        user: AppUser(
          userId: 'u-integration',
          username: 'integration',
          firstName: 'Integration',
          isPlatformUser: true,
        ),
        selectedStore: SelectedStore(
          storeId: 's-1',
          storeName: 'Nathan Medicals A',
          storeCode: 'NMA',
        ),
      );
}

/// The real tab shell with the real tab screens. The Sync branch is stubbed
/// because `SyncStatusScreen` reaches for the network on build, which would
/// make this test depend on a reachable HO server.
GoRouter _router() => GoRouter(
      initialLocation: AppRoutes.homePath,
      routes: [
        StatefulShellRoute.indexedStack(
          builder: (_, __, shell) => AppShell(navigationShell: shell),
          branches: [
            _branch(AppRoutes.homePath, const DashboardScreen()),
            StatefulShellBranch(
              routes: [
                GoRoute(
                  path: AppRoutes.capturePath,
                  builder: (_, __) => const CaptureScreen(),
                  routes: [
                    GoRoute(
                      path: AppRoutes.captureQueuePath,
                      name: AppRoutes.captureQueue,
                      builder: (_, __) => const CaptureQueueScreen(),
                    ),
                  ],
                ),
              ],
            ),
            _branch(AppRoutes.procurePath, const ProcurementHubScreen()),
            _branch(
              AppRoutes.syncPath,
              const Scaffold(body: Center(child: Text('sync stub'))),
            ),
            _branch(AppRoutes.morePath, const MoreScreen()),
          ],
        ),
      ],
    );

StatefulShellBranch _branch(String path, Widget screen) => StatefulShellBranch(
      routes: [GoRoute(path: path, builder: (_, __) => screen)],
    );

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('the real tab shell renders and switches between real screens', (
    tester,
  ) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authControllerProvider.overrideWith(_ReadyAuthController.new),
          // Dashboard watches the agent stream; keep it quiet and offline.
          agentStateProvider.overrideWith(
            (ref) => Stream<AgentState>.value(const AgentState()),
          ),
        ],
        child: MaterialApp.router(
          theme: AppTheme.dark,
          routerConfig: _router(),
        ),
      ),
    );
    await tester.pumpAndSettle();

    // Every tab is present and Home is the landing branch.
    expect(find.byType(NavigationBar), findsOneWidget);
    for (final section in AppSection.values) {
      expect(find.text(section.label), findsOneWidget, reason: section.name);
    }
    expect(find.text('Axythic'), findsOneWidget);

    // Each real screen builds without throwing when its tab is selected.
    await tester.tap(find.text('Capture'));
    await tester.pumpAndSettle();
    // Exercises the real capture launcher against the real Drift queue stream
    // and the real documents directory — neither is stubbed here.
    expect(find.text('Scan a supplier invoice'), findsOneWidget);
    expect(find.text('Open camera'), findsOneWidget);

    // Into the queue and back: this is the one screen that reads Drift through
    // a live stream and renders file-backed thumbnails, so it is worth
    // exercising on a real device runtime rather than only in a fake-async
    // widget test.
    await tester.tap(find.text('View all'));
    await tester.pumpAndSettle();
    expect(find.text('Capture queue'), findsOneWidget);
    expect(find.textContaining('Nothing captured yet'), findsOneWidget);

    await tester.pageBack();
    await tester.pumpAndSettle();
    expect(find.text('Scan a supplier invoice'), findsOneWidget);

    await tester.tap(find.text('Procure'));
    await tester.pumpAndSettle();
    expect(find.text('Procurement'), findsOneWidget);
    expect(find.text('Purchase Workspace'), findsOneWidget);
    expect(find.text('Legacy Order Console'), findsOneWidget);

    await tester.tap(find.text('More'));
    await tester.pumpAndSettle();
    expect(find.text('Nathan Medicals A'), findsOneWidget);
    expect(find.text('Reports'), findsOneWidget);
    // Device Status, Configuration Status and Agent Settings moved behind
    // Settings, so More is short enough again that Sign out is on screen
    // without scrolling. That was the point of the grouping.
    expect(find.text('Settings'), findsOneWidget);
    expect(find.text('Sign out'), findsOneWidget);
    expect(
      tester.getRect(find.text('Sign out')).bottom,
      lessThanOrEqualTo(
          tester.view.physicalSize.height / tester.view.devicePixelRatio),
      reason: 'grouping existed to bring Sign out back above the fold',
    );

    // Back to Home, and the bar tracks the active branch.
    await tester.tap(find.text('Home'));
    await tester.pumpAndSettle();
    expect(
      tester.widget<NavigationBar>(find.byType(NavigationBar)).selectedIndex,
      AppSection.home.index,
    );
    expect(tester.takeException(), isNull);
  });
}
