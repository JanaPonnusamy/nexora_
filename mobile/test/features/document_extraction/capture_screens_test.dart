import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';

import 'package:nexora_mobile/core/database/app_database.dart';
import 'package:nexora_mobile/core/di/capture_providers.dart';
import 'package:nexora_mobile/core/router/app_routes.dart';
import 'package:nexora_mobile/core/theme/app_theme.dart';
import 'package:nexora_mobile/features/document_extraction/application/capture_session_controller.dart';
import 'package:nexora_mobile/features/document_extraction/data/capture_queue_repository.dart';
import 'package:nexora_mobile/features/document_extraction/domain/capture_quality.dart';
import 'package:nexora_mobile/features/document_extraction/domain/document_status.dart';
import 'package:nexora_mobile/features/document_extraction/presentation/capture_screen.dart';
import 'package:nexora_mobile/features/document_extraction/presentation/widgets/capture_page_strip.dart';
import 'package:nexora_mobile/features/document_extraction/presentation/widgets/quality_banner.dart';

/// Renders the capture surfaces through the real theme and a real paint pass.
///
/// This exists because of the `StatusCard` regression recorded in the mobile
/// handoff: a decoration Flutter rejects at paint time passed both `analyze`
/// and the widget tests of the day, because nothing ever rendered the widget.
///
/// Everything the screens would otherwise reach for — the Drift stream, the
/// camera, the file system — is provided as plain data. `testWidgets` runs its
/// body in a fake-async zone, so awaiting real I/O inside one deadlocks the
/// test rather than failing it; the seams below keep that out entirely.
/// `CameraCaptureScreen` is verified on a device instead, for the same reason.
void main() {
  final capturedAt = DateTime(2026, 8, 16, 9, 30);

  CaptureJob job(DocumentStatus status) => CaptureJob(
        batch: CaptureBatch(
          id: 1,
          tenantId: 't-1',
          status: status.wire,
          pageCount: 2,
          attemptCount: 0,
          capturedAt: capturedAt,
          updatedAt: capturedAt,
          isExported: false,
        ),
        pages: const [],
      );

  CapturedPage page(QualityVerdict verdict) => CapturedPage(
        filePath: '/tmp/nonexistent/page_01.jpg',
        byteSize: 1024,
        quality: CaptureQuality(
          sharpness: 200,
          glareRatio: 0,
          brightness: 150,
          sourceWidth: 1600,
          sourceHeight: 2000,
          findings: verdict == QualityVerdict.good
              ? const []
              : [QualityFinding(QualityIssue.blurred, verdict)],
        ),
      );

  Widget host({
    List<CaptureJob> queue = const [],
    List<CapturedPage> session = const [],
  }) {
    return ProviderScope(
      overrides: [
        captureQueueStreamProvider.overrideWith((_) => Stream.value(queue)),
        captureSessionProvider.overrideWith(() => _SeededSession(session)),
      ],
      child: MaterialApp.router(
        theme: AppTheme.dark,
        routerConfig: GoRouter(
          initialLocation: AppRoutes.capturePath,
          routes: [
            GoRoute(
              path: AppRoutes.capturePath,
              name: AppRoutes.capture,
              builder: (_, __) => const CaptureScreen(),
            ),
          ],
        ),
      ),
    );
  }

  group('CaptureScreen', () {
    testWidgets('leads with the scan action over an empty queue',
        (tester) async {
      await tester.pumpWidget(host());
      await tester.pumpAndSettle();

      expect(find.text('Scan a supplier invoice'), findsOneWidget);
      expect(find.text('Open camera'), findsOneWidget);
      expect(find.text('Import from photos'), findsOneWidget);
      expect(
        find.text('Nothing waiting. Captured documents show up here.'),
        findsOneWidget,
      );
      expect(tester.takeException(), isNull);
    });

    testWidgets('counts what is waiting, processing, ready and failed',
        (tester) async {
      await tester.pumpWidget(
        host(
          queue: [
            job(DocumentStatus.pendingUpload),
            job(DocumentStatus.ocrRunning),
            job(DocumentStatus.reviewPending),
            job(DocumentStatus.failed),
          ],
        ),
      );
      await tester.pumpAndSettle();

      for (final label in ['Waiting', 'Processing', 'To review', 'Failed']) {
        expect(find.text(label), findsOneWidget);
      }
      // One of each state.
      expect(find.text('1'), findsNWidgets(4));
      expect(tester.takeException(), isNull);
    });

    testWidgets('offers to resume a document left half-captured',
        (tester) async {
      await tester.pumpWidget(
        host(
          session: [page(QualityVerdict.good), page(QualityVerdict.reject)],
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Unfinished document — 2 pages'), findsOneWidget);
      expect(find.text('1 flagged'), findsOneWidget);
      expect(find.text('Resume'), findsOneWidget);
      expect(find.text('Discard'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('says nothing about a session with no pages', (tester) async {
      await tester.pumpWidget(host());
      await tester.pumpAndSettle();

      expect(find.textContaining('Unfinished document'), findsNothing);
      expect(tester.takeException(), isNull);
    });
  });

  group('CapturePageStrip', () {
    testWidgets('numbers every page and marks the flagged ones',
        (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          theme: AppTheme.dark,
          home: Scaffold(
            body: CapturePageStrip(
              pages: [
                page(QualityVerdict.good),
                page(QualityVerdict.warn),
                page(QualityVerdict.reject),
              ],
              onRemove: (_) {},
            ),
          ),
        ),
      );
      await tester.pump();

      expect(find.text('1'), findsOneWidget);
      expect(find.text('3'), findsOneWidget);
      expect(find.byIcon(Icons.info_rounded), findsOneWidget);
      expect(find.byIcon(Icons.error_rounded), findsOneWidget);
      // One delete affordance per page.
      expect(find.byIcon(Icons.close_rounded), findsNWidgets(3));
      expect(tester.takeException(), isNull);
    });

    testWidgets('removing a page reports its index', (tester) async {
      final removed = <int>[];
      await tester.pumpWidget(
        MaterialApp(
          theme: AppTheme.dark,
          home: Scaffold(
            body: CapturePageStrip(
              pages: [page(QualityVerdict.good), page(QualityVerdict.good)],
              onRemove: removed.add,
            ),
          ),
        ),
      );
      await tester.pump();

      await tester.tap(find.byIcon(Icons.close_rounded).last);
      await tester.pump();

      expect(removed, [1]);
    });
  });

  group('QualityBanner', () {
    Widget banner(CaptureQuality quality, {VoidCallback? onRetake}) =>
        MaterialApp(
          theme: AppTheme.dark,
          home: Scaffold(
            body: QualityBanner(
              quality: quality,
              onRetake: onRetake ?? () {},
              onDismiss: () {},
            ),
          ),
        );

    testWidgets('a rejection names the problem and offers a retake',
        (tester) async {
      await tester.pumpWidget(banner(page(QualityVerdict.reject).quality));
      await tester.pump();

      expect(find.text('Blurry — retake recommended'), findsOneWidget);
      expect(find.text(QualityIssue.blurred.advice), findsOneWidget);
      expect(find.text('Retake'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('a warning stays usable rather than blocking', (tester) async {
      await tester.pumpWidget(banner(page(QualityVerdict.warn).quality));
      await tester.pump();

      expect(find.text('Blurry — still usable'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('a clean page has nothing to retake', (tester) async {
      await tester.pumpWidget(banner(CaptureQuality.unknown));
      await tester.pump();

      expect(find.text('Looks good'), findsOneWidget);
      expect(find.text('Retake'), findsNothing);
      expect(tester.takeException(), isNull);
    });

    testWidgets('the retake action fires', (tester) async {
      var retaken = 0;
      await tester.pumpWidget(
        banner(page(QualityVerdict.reject).quality, onRetake: () => retaken++),
      );
      await tester.pump();

      await tester.tap(find.text('Retake'));
      await tester.pump();

      expect(retaken, 1);
    });
  });
}

/// A capture session pinned to a fixed set of pages, so the screen can be
/// rendered without touching the camera, the processor or the file system.
class _SeededSession extends CaptureSessionController {
  _SeededSession(this._pages);

  final List<CapturedPage> _pages;

  @override
  CaptureSessionState build() =>
      CaptureSessionState(sessionId: 'test-session', pages: _pages);
}
