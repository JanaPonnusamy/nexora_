import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:nexora_mobile/core/config/app_config.dart';
import 'package:nexora_mobile/core/config/app_environment.dart';
import 'package:nexora_mobile/core/database/app_database.dart';
import 'package:nexora_mobile/core/di/outbox_providers.dart';
import 'package:nexora_mobile/core/di/providers.dart';
import 'package:nexora_mobile/core/outbox/outbox_repository.dart';
import 'package:nexora_mobile/core/theme/app_theme.dart';
import 'package:nexora_mobile/features/settings/presentation/pending_changes_screen.dart';
import 'package:nexora_mobile/features/settings/presentation/settings_screen.dart';

/// These screens are fed plain rows through provider overrides rather than a
/// real database (§3.11). A `testWidgets` body runs in fake async and a Drift
/// `watch()` stream needs real event-loop turns to deliver, so a screen backed
/// by a live query never settles — the file times out with no output at all,
/// which looks exactly like a hung compile.
OutboxEntry _entry({
  int id = 1,
  String kind = 'document.header',
  String summary = 'Invoice details',
  OutboxStatus status = OutboxStatus.pending,
  int attemptCount = 0,
  String? lastError,
}) {
  final now = DateTime(2026, 8, 18, 10);
  return OutboxEntry(
    id: id,
    kind: kind,
    scope: 'import:1',
    payload: '{}',
    status: status.name,
    attemptCount: attemptCount,
    lastError: lastError,
    summary: summary,
    createdAt: now,
    updatedAt: now,
  );
}

AppConfig _config({String url = 'http://localhost:8000'}) => AppConfig(
      environment: AppEnvironment.dev,
      apiBaseUrl: url,
      connectTimeout: const Duration(seconds: 15),
      receiveTimeout: const Duration(seconds: 45),
      enableVerboseLogging: true,
    );

Widget _harness(
  Widget screen, {
  List<OutboxEntry> outstanding = const [],
  AppConfig? config,
}) =>
    ProviderScope(
      overrides: [
        appConfigProvider.overrideWithValue(config ?? _config()),
        outboxOutstandingProvider
            .overrideWith((ref) => Stream.value(outstanding)),
      ],
      child: MaterialApp(theme: AppTheme.dark, home: screen),
    );

/// Tall enough that the ListView builds every section — `ListView.builder` only
/// builds what fits, so a short viewport silently hides half the assertions.
void _tallPhone(WidgetTester tester) {
  tester.view.physicalSize = const Size(390, 1600);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
}

void main() {
  group('SettingsScreen', () {
    testWidgets('renders every section without throwing', (tester) async {
      _tallPhone(tester);

      await tester.pumpWidget(_harness(const SettingsScreen()));
      await tester.pump();

      for (final section in [
        'YOUR CHANGES',
        'SECURITY',
        'STORAGE',
        'DIAGNOSTICS',
      ]) {
        expect(find.text(section), findsOneWidget, reason: section);
      }
      expect(tester.takeException(), isNull);
    });

    testWidgets('does not expose backend or environment details',
        (tester) async {
      _tallPhone(tester);

      await tester.pumpWidget(_harness(const SettingsScreen()));
      await tester.pump();

      expect(find.text('SERVER'), findsNothing);
      expect(find.text('Backend'), findsNothing);
      expect(find.text('Environment'), findsNothing);
      expect(find.textContaining('Not encrypted'), findsNothing);
    });

    testWidgets('says everything is synced when nothing is owed',
        (tester) async {
      _tallPhone(tester);

      await tester.pumpWidget(_harness(const SettingsScreen()));
      await tester.pump();

      expect(find.text('Everything is synced'), findsOneWidget);
    });

    testWidgets('counts what is waiting', (tester) async {
      _tallPhone(tester);

      await tester.pumpWidget(
        _harness(
          const SettingsScreen(),
          outstanding: [_entry(), _entry(id: 2)],
        ),
      );
      await tester.pump();

      expect(find.text('2 waiting to be sent'), findsOneWidget);
    });

    testWidgets('leads with the ones that need a person', (tester) async {
      _tallPhone(tester);

      await tester.pumpWidget(
        _harness(
          const SettingsScreen(),
          outstanding: [
            _entry(),
            _entry(id: 2, status: OutboxStatus.deadLetter),
          ],
        ),
      );
      await tester.pump();

      expect(find.text('1 of 2 need your attention'), findsOneWidget);
    });
  });

  group('PendingChangesScreen', () {
    testWidgets('an empty outbox says it is safe to close the app',
        (tester) async {
      await tester.pumpWidget(_harness(const PendingChangesScreen()));
      await tester.pump();

      expect(find.textContaining('Everything is synced'), findsOneWidget);
    });

    testWidgets('a waiting change explains itself without alarming anyone',
        (tester) async {
      await tester.pumpWidget(
        _harness(const PendingChangesScreen(), outstanding: [_entry()]),
      );
      await tester.pump();

      expect(find.text('Invoice details'), findsOneWidget);
      expect(find.text('Waiting'), findsOneWidget);
      expect(find.textContaining('back online'), findsOneWidget);
      // Retry and Discard belong to entries that need a person, not to one
      // that is simply waiting for signal.
      expect(find.text('Try again'), findsNothing);
      expect(find.text('Discard'), findsNothing);
    });

    testWidgets('a given-up change asks for a person and offers both ways out',
        (tester) async {
      await tester.pumpWidget(
        _harness(
          const PendingChangesScreen(),
          outstanding: [
            _entry(
              kind: 'document.item',
              summary: 'A line on this invoice',
              status: OutboxStatus.deadLetter,
              attemptCount: 8,
              lastError: 'Quantity must be positive.',
            ),
          ],
        ),
      );
      await tester.pump();

      expect(find.text('Needs you'), findsOneWidget);
      expect(find.text('Quantity must be positive.'), findsOneWidget);
      expect(find.text('Try again'), findsOneWidget);
      expect(find.text('Discard'), findsOneWidget);
      expect(
        tester.takeException(),
        isNull,
        reason: 'buttons in a Row need an explicit minimumSize (§3.8)',
      );
    });

    testWidgets(
      'discarding is confirmed first, and names the loss — it is the one '
      'action on this screen that throws work away',
      (tester) async {
        await tester.pumpWidget(
          _harness(
            const PendingChangesScreen(),
            outstanding: [
              _entry(
                summary: 'A line on this invoice',
                status: OutboxStatus.deadLetter,
                lastError: 'rejected',
              ),
            ],
          ),
        );
        await tester.pump();

        await tester.tap(find.text('Discard'));
        await tester.pumpAndSettle();

        expect(find.text('Discard this change?'), findsOneWidget);
        expect(find.textContaining('cannot be undone'), findsOneWidget);
        expect(find.text('Keep it'), findsOneWidget);
      },
    );

    testWidgets('a retrying change reports how many tries it has had',
        (tester) async {
      await tester.pumpWidget(
        _harness(
          const PendingChangesScreen(),
          outstanding: [
            _entry(attemptCount: 3, lastError: 'Server unavailable.'),
          ],
        ),
      );
      await tester.pump();

      expect(find.textContaining('Tried 3 times'), findsOneWidget);
      expect(find.textContaining('Server unavailable.'), findsOneWidget);
    });
  });
}
