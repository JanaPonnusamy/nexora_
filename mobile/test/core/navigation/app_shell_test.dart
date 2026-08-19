import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';

import 'package:nexora_mobile/core/navigation/app_section.dart';
import 'package:nexora_mobile/core/navigation/app_shell.dart';
import 'package:nexora_mobile/core/theme/app_theme.dart';

/// Minimal stand-in for the real router: same branch order as the app, but a
/// bare screen per branch and no auth redirects.
GoRouter _testRouter() => GoRouter(
      initialLocation: AppSection.home.path,
      routes: [
        StatefulShellRoute.indexedStack(
          builder: (_, __, shell) => AppShell(navigationShell: shell),
          branches: [
            for (final section in AppSection.values)
              StatefulShellBranch(
                routes: [
                  GoRoute(
                    path: section.path,
                    builder: (_, __) => Scaffold(
                        body: Center(child: Text('${section.name} body'))),
                  ),
                ],
              ),
          ],
        ),
      ],
    );

Future<void> _pump(
  WidgetTester tester, {
  required List<AppSection> visible,
}) async {
  await tester.pumpWidget(
    ProviderScope(
      overrides: [
        visibleSectionsProvider.overrideWithValue(visible),
      ],
      child: MaterialApp.router(
        theme: AppTheme.dark,
        routerConfig: _testRouter(),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  group('AppShell', () {
    testWidgets('renders one destination per visible section', (tester) async {
      await _pump(tester, visible: AppSection.values);

      expect(find.byType(NavigationBar), findsOneWidget);
      for (final section in AppSection.values) {
        expect(find.text(section.label), findsOneWidget);
      }
    });

    testWidgets('hidden sections are absent from the bar', (tester) async {
      await _pump(
        tester,
        visible: const [AppSection.home, AppSection.sync, AppSection.more],
      );

      expect(find.text('Home'), findsOneWidget);
      expect(find.text('Sync'), findsOneWidget);
      expect(find.text('More'), findsOneWidget);
      expect(find.text('Capture'), findsNothing);
      expect(find.text('Procure'), findsNothing);
    });

    testWidgets('tapping a tab switches to its branch', (tester) async {
      await _pump(tester, visible: AppSection.values);
      expect(find.text('home body'), findsOneWidget);

      await tester.tap(find.text('Procure'));
      await tester.pumpAndSettle();

      expect(find.text('procure body'), findsOneWidget);
      expect(
        tester.widget<NavigationBar>(find.byType(NavigationBar)).selectedIndex,
        AppSection.procure.index,
      );
    });

    testWidgets(
      'a filtered bar maps its index to the right branch, not its own position',
      (tester) async {
        // With Capture and Procure hidden, Sync sits at bar position 1 but is
        // branch 3. Selecting by bar index alone would land on Capture.
        await _pump(
          tester,
          visible: const [AppSection.home, AppSection.sync, AppSection.more],
        );

        await tester.tap(find.text('Sync'));
        await tester.pumpAndSettle();

        expect(find.text('sync body'), findsOneWidget);
        expect(find.text('capture body'), findsNothing);
        expect(
          tester
              .widget<NavigationBar>(find.byType(NavigationBar))
              .selectedIndex,
          1, // position within the visible list
        );
      },
    );

    testWidgets('an active branch the user cannot see falls back to index 0', (
      tester,
    ) async {
      // Start on Home (branch 0) with a visible list that excludes it — the
      // shape of a mid-session permission change. NavigationBar would assert
      // on a -1 index.
      await _pump(
        tester,
        visible: const [AppSection.sync, AppSection.more],
      );

      expect(tester.takeException(), isNull);
      expect(
        tester.widget<NavigationBar>(find.byType(NavigationBar)).selectedIndex,
        0,
      );
    });
  });
}
