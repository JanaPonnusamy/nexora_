import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:image/image.dart' as img;
import 'package:integration_test/integration_test.dart';

import 'package:nexora_mobile/core/router/app_routes.dart';
import 'package:nexora_mobile/core/theme/app_theme.dart';
import 'package:nexora_mobile/features/document_extraction/application/document_export_controller.dart';
import 'package:nexora_mobile/features/document_extraction/application/document_review_controller.dart';
import 'package:nexora_mobile/features/document_extraction/domain/document_review.dart';
import 'package:nexora_mobile/features/document_extraction/presentation/document_review_screen.dart';
import 'package:nexora_mobile/features/document_extraction/presentation/widgets/document_page_view.dart';
import 'package:nexora_mobile/features/document_extraction/presentation/widgets/review_item_card.dart';

/// The review screen on a real device runtime.
///
/// Widget tests run in a fake-async zone with a fake image codec; this file
/// exists for the two things that only a real run proves — that the screen
/// lays out and paints at phone width through the real theme, and that a page
/// image actually decodes and displays in the viewer.
///
/// Only the two seams that would need a server are stubbed: the review payload
/// and the page bytes.
void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  const importId = 77;

  final sharedFiles = <File>[];

  final review = DocumentReview.fromJson({
    'import_id': importId,
    'status': 'REVIEW_PENDING',
    'header': {
      'import_id': importId,
      'invoice_number': 'SI/26-27/4821',
      'invoice_date': '2026-08-11',
      'net_amount': 12480.55,
      'gross_amount': 11890.0,
      'cgst_amount': 295.25,
      'sgst_amount': 295.30,
      'item_count': 3,
      'page_count': 2,
      'ocr_confidence': 0.86,
    },
    'supplier': {
      'supplier_name': 'Sri Balaji Pharma Distributors',
      'gst_number': '33AABCS1429B1ZP',
      'supplier_match_method': 'GST',
      'supplier_match_confidence': 0.97,
      'is_supplier_unknown': false,
    },
    'items': [
      {
        'item_id': 1,
        'line_number': 1,
        'normalized_product_name': 'Dolo 650mg Tablet',
        'product_code': 'PRD-10041',
        'pack': '15s',
        'batch_number': 'DL2411',
        'expiry_date': '2027-11-30',
        'quantity': 40,
        'free_quantity': 4,
        'purchase_rate': 21.5,
        'mrp': 30.0,
        'gst_percent': 12,
        'amount': 860.0,
        'confidence': 0.94,
      },
      {
        'item_id': 2,
        'line_number': 2,
        // The line that needs a person: no product code, unreadable batch, an
        // expiry OCR could not parse, low confidence.
        'ocr_product_name': 'AMOXYCLLIN 625 TAB',
        'batch_number': '-',
        'expiry_raw': '13/26',
        'quantity': 60,
        'purchase_rate': 92.4,
        'amount': 5544.0,
        'confidence': 0.41,
      },
      {
        'item_id': 3,
        'line_number': 3,
        'normalized_product_name': 'Pantoprazole 40mg Injection',
        'product_code': 'PRD-88213',
        'batch_number': 'PN0912',
        'expiry_date': '2027-02-28',
        'quantity': 25,
        'purchase_rate': 242.6,
        'mrp': 310.0,
        'amount': 6065.0,
        'confidence': 0.79,
      },
    ],
    'validation': {
      'validation_status': 'WARNING',
      'findings': [
        {
          'rule_code': 'MISSING_PRODUCT_CODE',
          'severity': 'WARNING',
          'item_id': 2,
          'message': 'Product could not be resolved to a ProductCode.',
        },
        {
          'rule_code': 'INVALID_EXPIRY',
          'severity': 'WARNING',
          'field': 'expiry_raw',
          'item_id': 2,
          'message': "Expiry '13/26' could not be parsed.",
        },
      ],
    },
  });

  /// A real PNG, encoded on the device, so the viewer's decode path runs for
  /// real rather than against a fake codec.
  Uint8List pageBytes() {
    final page = img.Image(width: 400, height: 560);
    img.fill(page, color: img.ColorRgb8(240, 240, 235));
    img.fillRect(page,
        x1: 30, y1: 40, x2: 370, y2: 70, color: img.ColorRgb8(60, 60, 60));
    return Uint8List.fromList(img.encodePng(page));
  }

  Widget app({DocumentReview? payload}) => ProviderScope(
        overrides: [
          documentReviewProvider(importId)
              .overrideWith((ref) => payload ?? review),
          exportDirectoryProvider
              .overrideWithValue(() async => Directory.systemTemp),
          fileSharerProvider.overrideWithValue(
            (File file, {String? subject, Rect? sharePositionOrigin}) async =>
                sharedFiles.add(file),
          ),
          for (final source in DocumentImageSource.values)
            for (var page = 1; page <= 2; page++)
              documentPageImageProvider(
                (importId: importId, page: page, source: source),
              ).overrideWith((ref) async => pageBytes()),
        ],
        child: MaterialApp.router(
          theme: AppTheme.dark,
          routerConfig: GoRouter(
            initialLocation: AppRoutes.documentReviewLocation(importId),
            routes: [
              GoRoute(
                path: AppRoutes.capturePath,
                builder: (_, __) => const Scaffold(body: Text('capture')),
                routes: [
                  GoRoute(
                    path: AppRoutes.documentReviewPath,
                    builder: (_, state) => DocumentReviewScreen(
                      importId: int.parse(state.pathParameters['importId']!),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      );

  testWidgets('a committed invoice offers the export in the same bar',
      (tester) async {
    sharedFiles.clear();
    final saved = DocumentReview.fromJson({
      'import_id': importId,
      'status': 'SAVED',
      'header': {
        'import_id': importId,
        'invoice_number': 'SI/26-27/4821',
        'net_amount': 12480.55,
        'page_count': 2,
      },
      'supplier': {'supplier_name': 'Sri Balaji Pharma Distributors'},
      'items': const [],
    });

    await tester.pumpWidget(app(payload: saved));
    await tester.pumpAndSettle();

    expect(find.text('Saved and ready to export.'), findsOneWidget);
    expect(find.text('Export'), findsOneWidget);
    expect(find.text('Save invoice'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('the review screen lays out and paints at phone width',
      (tester) async {
    await tester.pumpWidget(app());
    await tester.pumpAndSettle();

    expect(find.text('Invoice #77'), findsOneWidget);
    expect(find.text('Sri Balaji Pharma Distributors'), findsOneWidget);
    expect(find.text('SI/26-27/4821'), findsOneWidget);
    expect(find.text('3 lines'), findsOneWidget);
    expect(find.text('1 needs a look'), findsOneWidget);
    expect(find.text('Save invoice'), findsOneWidget);
    expect(tester.takeException(), isNull);

    // Down to the flagged line and back up: every card paints, and the sticky
    // save bar stays put.
    await tester.scrollUntilVisible(find.text('AMOXYCLLIN 625 TAB'), 240);
    await tester.pumpAndSettle();
    expect(find.text("Expiry '13/26' could not be parsed."), findsOneWidget);
    expect(find.text('Save invoice'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a header correction opens a real sheet over the screen',
      (tester) async {
    await tester.pumpWidget(app());
    await tester.pumpAndSettle();

    await tester.tap(find.text('Edit').first);
    await tester.pumpAndSettle();

    expect(find.text('Invoice details'), findsOneWidget);
    expect(find.text('SI/26-27/4821'), findsWidgets);

    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    expect(find.text('Invoice details'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a line correction offers what OCR read for the expiry',
      (tester) async {
    await tester.pumpWidget(app());
    await tester.pumpAndSettle();

    await tester.scrollUntilVisible(find.text('AMOXYCLLIN 625 TAB'), 240);
    await tester.pumpAndSettle();

    // The flagged line's own Edit button, not whichever card happens to be
    // first in the tree.
    final card = find.ancestor(
      of: find.text('AMOXYCLLIN 625 TAB'),
      matching: find.byType(ReviewItemCard),
    );
    final editLine =
        find.descendant(of: card, matching: find.text('Edit line'));
    await tester.ensureVisible(editLine);
    await tester.pumpAndSettle();
    await tester.tap(editLine);
    await tester.pumpAndSettle();

    expect(find.text('Line 2'), findsOneWidget);
    // The unparsed text is the reviewer's clue about what the date should be.
    expect(
      find.text('Read from the invoice as "13/26"'),
      findsOneWidget,
    );

    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
  });

  testWidgets('the page viewer decodes and shows the captured page',
      (tester) async {
    await tester.pumpWidget(app());
    await tester.pumpAndSettle();

    await tester.tap(find.byIcon(Icons.image_outlined));
    await tester.pumpAndSettle();

    expect(find.text('Page 1 of 2'), findsOneWidget);
    // Decoded on the device: a fake codec would never get here.
    expect(find.byType(Image), findsOneWidget);
    expect(find.byType(InteractiveViewer), findsOneWidget);

    await tester.tap(find.text('Original'));
    await tester.pumpAndSettle();
    expect(find.text('Cleaned'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
