import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';

import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/core/theme/app_theme.dart';
import 'package:nexora_mobile/features/document_extraction/application/document_review_controller.dart';
import 'package:nexora_mobile/features/document_extraction/domain/document_review.dart';
import 'package:nexora_mobile/features/document_extraction/presentation/document_review_screen.dart';
import 'package:nexora_mobile/features/document_extraction/presentation/widgets/review_summary_card.dart';

/// Renders the review surfaces through the real theme and a real paint pass.
///
/// The payload is fed in as plain data: `testWidgets` runs its body in a
/// fake-async zone, so a screen that awaited a real HTTP call or a Drift query
/// here would deadlock the file rather than fail it.
void main() {
  const importId = 12;

  Map<String, dynamic> payload({
    Map<String, dynamic>? header,
    Map<String, dynamic>? supplier,
    List<Map<String, dynamic>>? items,
    Object? validation,
    String status = 'REVIEW_PENDING',
  }) =>
      {
        'import_id': importId,
        'status': status,
        'header': {
          'import_id': importId,
          'invoice_number': 'INV-9001',
          'invoice_date': '2026-08-01',
          'net_amount': 300.0,
          'page_count': 2,
          ...?header,
        },
        'supplier': {
          'supplier_name': 'Acme Pharma',
          'matched_supplier_code': 'SUP01',
          'supplier_match_method': 'GST',
          'supplier_match_confidence': 0.94,
          'is_supplier_unknown': false,
          ...?supplier,
        },
        'items': items ??
            [
              {
                'item_id': 1,
                'line_number': 1,
                'normalized_product_name': 'Paracetamol 500mg',
                'product_code': 'P-100',
                'batch_number': 'B1234',
                'expiry_date': '2027-06-30',
                'quantity': 10,
                'purchase_rate': 10.0,
                'amount': 100.0,
                'confidence': 0.95,
              },
              {
                'item_id': 2,
                'line_number': 2,
                'normalized_product_name': 'Amoxicillin 250mg',
                'batch_number': '--',
                'quantity': 20,
                'amount': 200.0,
                'confidence': 0.4,
              },
            ],
        if (validation != null) 'validation': validation,
      };

  Widget host(
    Map<String, dynamic> json, {
    DocumentReviewController Function(Ref ref)? controller,
  }) {
    return ProviderScope(
      overrides: [
        documentReviewProvider(importId).overrideWith(
          (ref) => DocumentReview.fromJson(json),
        ),
        if (controller != null)
          documentReviewControllerProvider.overrideWith(controller),
      ],
      child: MaterialApp.router(
        theme: AppTheme.dark,
        routerConfig: GoRouter(
          initialLocation: '/review',
          routes: [
            GoRoute(
              path: '/review',
              builder: (_, __) =>
                  const DocumentReviewScreen(importId: importId),
            ),
          ],
        ),
      ),
    );
  }

  /// Tall enough that a sliver list builds every card — `SliverList.builder`
  /// only builds what fits, so a short viewport would pass tests about rows
  /// that were never rendered.
  void useTallScreen(WidgetTester tester) {
    tester.view.physicalSize = const Size(1200, 4000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
  }

  group('DocumentReviewScreen', () {
    testWidgets('renders the invoice, its lines and the save action',
        (tester) async {
      useTallScreen(tester);
      await tester.pumpWidget(host(payload()));
      await tester.pumpAndSettle();

      expect(find.text('Invoice #12'), findsOneWidget);
      expect(find.text('Acme Pharma'), findsOneWidget);
      expect(find.text('INV-9001'), findsOneWidget);
      expect(find.text('Paracetamol 500mg'), findsOneWidget);
      expect(find.text('Amoxicillin 250mg'), findsOneWidget);
      expect(find.text('2 lines'), findsOneWidget);
      expect(find.text('Save invoice'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('leads with what is wrong', (tester) async {
      useTallScreen(tester);
      await tester.pumpWidget(
        host(
          payload(
            validation: {
              'validation_status': 'FAILED',
              'findings': [
                {
                  'rule_code': 'MISSING_REQUIRED_FIELD',
                  'severity': 'ERROR',
                  'field': 'net_amount',
                  'message': 'Net Amount is missing.',
                },
                {
                  'rule_code': 'INVALID_BATCH',
                  'severity': 'WARNING',
                  'item_id': 2,
                  'message': 'Batch number looks invalid or missing.',
                },
              ],
            },
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('1 error · 1 warning'), findsOneWidget);
      expect(find.text('Net Amount is missing.'), findsOneWidget);
      // A finding about one line belongs on that line, not in a list the
      // reviewer has to match up by hand.
      expect(
        find.text('Batch number looks invalid or missing.'),
        findsOneWidget,
      );
      expect(find.text('Save anyway'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('a missing required field reads as a gap, not a dash',
        (tester) async {
      useTallScreen(tester);
      await tester.pumpWidget(
        host(payload(header: {'invoice_number': null, 'net_amount': null})),
      );
      await tester.pumpAndSettle();

      expect(find.text('Missing'), findsNWidgets(2));
      expect(tester.takeException(), isNull);
    });

    testWidgets('an unmatched supplier is offered for assignment',
        (tester) async {
      useTallScreen(tester);
      await tester.pumpWidget(
        host(
          payload(
            supplier: {
              'supplier_name': null,
              'matched_supplier_code': null,
              'supplier_match_method': null,
              'is_supplier_unknown': true,
            },
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Supplier not identified'), findsOneWidget);
      expect(find.text('Not matched to a supplier'), findsOneWidget);
      expect(find.text('Assign'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('flags the lines worth a second look', (tester) async {
      useTallScreen(tester);
      await tester.pumpWidget(host(payload()));
      await tester.pumpAndSettle();

      expect(find.text('1 needs a look'), findsOneWidget);
      expect(find.text('Missing product'), findsOneWidget);
      expect(find.text('Low confidence'), findsOneWidget);
      expect(find.text('Invalid batch'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('the flagged filter hides the lines that are fine',
        (tester) async {
      useTallScreen(tester);
      await tester.pumpWidget(host(payload()));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Only flagged'));
      await tester.pumpAndSettle();

      expect(find.text('Amoxicillin 250mg'), findsOneWidget);
      expect(find.text('Paracetamol 500mg'), findsNothing);
      expect(tester.takeException(), isNull);
    });

    testWidgets('shows both figures when the totals do not agree',
        (tester) async {
      useTallScreen(tester);
      await tester.pumpWidget(
        host(payload(header: {'net_amount': 340.0})),
      );
      await tester.pumpAndSettle();

      expect(find.text('1 total that does not match'), findsOneWidget);
      expect(find.text('300.00 vs 340.00'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('counts are shown as counts, not as amounts', (tester) async {
      // "2 lines" written as "2.00" reads as money, which is exactly the
      // confusion this card exists to prevent.
      useTallScreen(tester);
      await tester.pumpWidget(
        host(payload(header: {'item_count': 2, 'total_quantity': 30})),
      );
      await tester.pumpAndSettle();

      final summary = find.byType(ReviewSummaryCard);
      expect(
        find.descendant(of: summary, matching: find.text('2')),
        findsOneWidget,
      );
      expect(
        find.descendant(of: summary, matching: find.text('30')),
        findsOneWidget,
      );
      expect(find.text('2.00'), findsNothing);
      expect(find.text('30.00'), findsNothing);
      expect(tester.takeException(), isNull);
    });

    testWidgets('an excluded line stays visible but out of the invoice',
        (tester) async {
      useTallScreen(tester);
      await tester.pumpWidget(
        host(
          payload(
            items: [
              {
                'item_id': 1,
                'line_number': 1,
                'normalized_product_name': 'Paracetamol 500mg',
                'product_code': 'P-100',
                'batch_number': 'B1234',
                'amount': 100.0,
              },
              {
                'item_id': 2,
                'line_number': 2,
                'normalized_product_name': 'Sub total',
                'amount': 100.0,
                'is_excluded': true,
              },
            ],
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Sub total'), findsOneWidget);
      expect(find.text('Not part of this invoice'), findsOneWidget);
      expect(find.text('1 line'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });

    testWidgets('a saved invoice is shown, not edited — and offers the export',
        (tester) async {
      useTallScreen(tester);
      await tester.pumpWidget(host(payload(status: 'SAVED')));
      await tester.pumpAndSettle();

      // Export sits here rather than only in the queue: the moment after
      // saving is when someone wants to send the invoice on.
      expect(find.text('Saved and ready to export.'), findsOneWidget);
      expect(find.text('Export'), findsOneWidget);
      expect(find.text('Save invoice'), findsNothing);
      expect(find.text('Edit'), findsNothing);
      expect(find.text('Edit line'), findsNothing);
      expect(find.text('Change'), findsNothing);
      expect(tester.takeException(), isNull);
    });

    testWidgets('an exported invoice offers a fresh workbook, not an edit',
        (tester) async {
      useTallScreen(tester);
      await tester.pumpWidget(host(payload(status: 'EXPORTED')));
      await tester.pumpAndSettle();

      expect(find.text('Exported'), findsOneWidget);
      expect(find.text('Share again'), findsOneWidget);
      expect(find.text('Save invoice'), findsNothing);
      expect(find.text('Edit line'), findsNothing);
      expect(tester.takeException(), isNull);
    });

    testWidgets('saving runs through the controller', (tester) async {
      useTallScreen(tester);
      _RecordingController.saved.clear();
      await tester.pumpWidget(
        host(payload(), controller: _RecordingController.new),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Save invoice'));
      await tester.pumpAndSettle();

      expect(_RecordingController.saved, [importId]);
      expect(find.text('Invoice saved.'), findsOneWidget);
    });

    testWidgets('a payload that will not load offers a retry', (tester) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            documentReviewProvider(importId).overrideWith(
              (ref) => Future<DocumentReview>.error(
                const ApiException(
                    message: 'Import not found', statusCode: 404),
              ),
            ),
          ],
          child: MaterialApp(
            theme: AppTheme.dark,
            home: const DocumentReviewScreen(importId: importId),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('This invoice could not be opened'), findsOneWidget);
      expect(find.text('Import not found'), findsOneWidget);
      expect(find.text('Try again'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  });
}

/// Stands in for the real controller so the save bar can be exercised without
/// a server.
class _RecordingController extends DocumentReviewController {
  _RecordingController(super.ref);

  static final saved = <int>[];

  @override
  Future<ReviewActionResult> save(
    int importId, {
    int? batchId,
    bool force = false,
  }) async {
    saved.add(importId);
    return const ReviewActionResult(message: 'Invoice saved.');
  }
}
