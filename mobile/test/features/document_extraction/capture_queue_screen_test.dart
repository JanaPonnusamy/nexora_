import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';

import 'package:nexora_mobile/core/router/app_routes.dart';
import 'package:nexora_mobile/core/theme/app_theme.dart';
import 'package:nexora_mobile/features/document_extraction/application/capture_queue_controller.dart';
import 'package:nexora_mobile/features/document_extraction/application/capture_queue_entry.dart';
import 'package:nexora_mobile/features/document_extraction/presentation/capture_queue_screen.dart';
import 'package:nexora_mobile/features/document_extraction/presentation/widgets/capture_queue_card.dart';

/// Renders the queue through the real theme and a real paint pass.
///
/// The infinite-width assert that got through `analyze` last time came from a
/// themed button in a Row; this screen puts several in a Wrap, so every stage's
/// card is pumped here rather than trusted.
void main() {
  CaptureQueueEntry entry({
    required QueueStage stage,
    int batchId = 1,
    int? importId,
    String? detail,
    int flaggedPages = 0,
  }) {
    return CaptureQueueEntry(
      batchId: batchId,
      importId: importId,
      pageCount: 2,
      capturedAt: DateTime.now().subtract(const Duration(minutes: 3)),
      stage: stage,
      statusLabel: stage.name,
      detail: detail,
      actions: _actionsFor(stage),
      flaggedPages: flaggedPages,
      totalBytes: 900 * 1024,
    );
  }

  Widget host(List<CaptureQueueEntry> entries) {
    return ProviderScope(
      overrides: [
        captureQueueEntriesProvider.overrideWith(
          (_) => Stream.value(entries),
        ),
      ],
      child: MaterialApp(
        theme: AppTheme.dark,
        home: const CaptureQueueScreen(),
      ),
    );
  }

  testWidgets('every stage renders without a layout error', (tester) async {
    // The list is lazy, so a default-sized surface would only ever build the
    // first three cards — and the point here is that all seven paint.
    tester.view.physicalSize = const Size(1200, 5200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      host([
        for (final (i, stage) in QueueStage.values.indexed)
          entry(
            stage: stage,
            batchId: i + 1,
            importId: stage == QueueStage.waiting ? null : 100 + i,
            detail: 'Detail line for ${stage.name}.',
          ),
      ]),
    );
    // Not pumpAndSettle: a processing card carries an indeterminate progress
    // bar, which by design never stops animating.
    await tester.pump();
    await tester.pump();

    expect(
      find.byType(CaptureQueueCard),
      findsNWidgets(QueueStage.values.length),
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets('an empty queue explains itself', (tester) async {
    await tester.pumpWidget(host(const []));
    await tester.pumpAndSettle();

    expect(find.textContaining('Nothing captured yet'), findsOneWidget);
    expect(find.byType(CaptureQueueCard), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('the header leads with what needs a person', (tester) async {
    await tester.pumpWidget(
      host([
        entry(stage: QueueStage.failed, batchId: 1, importId: 1),
        entry(stage: QueueStage.processing, batchId: 2, importId: 2),
      ]),
    );
    await tester.pump();
    await tester.pump();

    expect(find.text('1 needs your attention'), findsOneWidget);
    expect(find.text('2 total'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a quiet queue says so rather than showing a zero',
      (tester) async {
    await tester.pumpWidget(
      host([entry(stage: QueueStage.exported, batchId: 1, importId: 1)]),
    );
    await tester.pumpAndSettle();

    expect(find.text('Everything is up to date'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a saved document is counted as work still outstanding',
      (tester) async {
    // Nothing is wrong with it, but the last step of the job — getting the
    // invoice into a workbook — has not happened, and "up to date" would hide
    // that.
    await tester.pumpWidget(
      host([entry(stage: QueueStage.saved, batchId: 1, importId: 1)]),
    );
    await tester.pumpAndSettle();

    expect(find.text('1 ready to export'), findsOneWidget);
    expect(find.text('Export'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('an exported document can still be shared again', (tester) async {
    // A workbook sent to the wrong person, or into a chat since cleared, has
    // to be re-sendable.
    await tester.pumpWidget(
      host([entry(stage: QueueStage.exported, batchId: 1, importId: 1)]),
    );
    await tester.pumpAndSettle();

    expect(find.text('Share again'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a stopped upload offers the button that unsticks it',
      (tester) async {
    await tester.pumpWidget(
      host([
        entry(
          stage: QueueStage.stopped,
          detail: 'Stopped after 6 attempts.',
        ),
      ]),
    );
    await tester.pumpAndSettle();

    expect(find.text('Upload now'), findsOneWidget);
    expect(find.text('Stopped after 6 attempts.'), findsOneWidget);
    expect(find.text('Delete'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a failed document offers a pipeline retry, not a re-upload',
      (tester) async {
    await tester.pumpWidget(
      host([entry(stage: QueueStage.failed, importId: 42)]),
    );
    await tester.pumpAndSettle();

    expect(find.text('Try again'), findsOneWidget);
    expect(find.text('Upload now'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('pages flagged at capture are surfaced on the card',
      (tester) async {
    await tester.pumpWidget(
      host([
        entry(stage: QueueStage.readyToReview, importId: 42, flaggedPages: 2),
      ]),
    );
    await tester.pumpAndSettle();

    expect(find.text('2 pages flagged at capture'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('deleting asks first, and warns when there is no other copy',
      (tester) async {
    await tester.pumpWidget(host([entry(stage: QueueStage.waiting)]));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Delete'));
    await tester.pumpAndSettle();

    expect(find.text('Delete this document?'), findsOneWidget);
    expect(
      find.textContaining('there is no other copy'),
      findsOneWidget,
    );

    await tester.tap(find.text('Keep'));
    await tester.pumpAndSettle();
    expect(find.byType(CaptureQueueCard), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('deleting an uploaded document warns about the server copy',
      (tester) async {
    await tester.pumpWidget(
      host([entry(stage: QueueStage.readyToReview, importId: 42)]),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Delete'));
    await tester.pumpAndSettle();

    expect(
      find.textContaining('extracted data on the server'),
      findsOneWidget,
    );
    expect(tester.takeException(), isNull);
  });

  group('Review', () {
    /// The queue inside a router, so the review button's navigation is
    /// exercised rather than assumed. The review route is a stub: what is
    /// being tested here is the location and the ids it carries.
    Widget routedHost(List<CaptureQueueEntry> entries) {
      return ProviderScope(
        overrides: [
          captureQueueEntriesProvider
              .overrideWith((_) => Stream.value(entries)),
        ],
        child: MaterialApp.router(
          theme: AppTheme.dark,
          routerConfig: GoRouter(
            initialLocation: AppRoutes.captureQueueFullPath,
            routes: [
              GoRoute(
                path: AppRoutes.capturePath,
                builder: (_, __) => const Scaffold(body: Text('capture')),
                routes: [
                  GoRoute(
                    path: AppRoutes.captureQueuePath,
                    builder: (_, __) => const CaptureQueueScreen(),
                  ),
                  GoRoute(
                    path: AppRoutes.documentReviewPath,
                    builder: (_, state) => Scaffold(
                      body: Text(
                        'review ${state.pathParameters['importId']} '
                        'batch ${state.uri.queryParameters['batch']}',
                      ),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      );
    }

    testWidgets('opens the review screen for the import behind the row',
        (tester) async {
      await tester.pumpWidget(
        routedHost([
          entry(stage: QueueStage.readyToReview, batchId: 7, importId: 42),
        ]),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Review'));
      await tester.pumpAndSettle();

      // The local batch travels with the import so a save can move this row
      // off "Ready to review".
      expect(find.text('review 42 batch 7'), findsOneWidget);
    });

    testWidgets('says so when there is nothing on the server to review',
        (tester) async {
      await tester.pumpWidget(
        routedHost([
          entry(stage: QueueStage.readyToReview, batchId: 7),
        ]),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Review'));
      await tester.pumpAndSettle();

      expect(
        find.text('This document has not reached the server yet.'),
        findsOneWidget,
      );
      expect(find.textContaining('review '), findsNothing);
    });
  });
}

Set<QueueAction> _actionsFor(QueueStage stage) => switch (stage) {
      QueueStage.waiting || QueueStage.retrying || QueueStage.stopped => {
          QueueAction.retryUpload,
          QueueAction.delete,
        },
      QueueStage.processing => {QueueAction.delete},
      QueueStage.readyToReview => {QueueAction.review, QueueAction.delete},
      QueueStage.saved || QueueStage.exported => {
          QueueAction.export,
          QueueAction.review,
          QueueAction.delete,
        },
      QueueStage.failed => {QueueAction.retryPipeline, QueueAction.delete},
    };
