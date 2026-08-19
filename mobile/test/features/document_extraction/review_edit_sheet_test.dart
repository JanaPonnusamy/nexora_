import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:nexora_mobile/core/theme/app_theme.dart';
import 'package:nexora_mobile/features/document_extraction/presentation/widgets/review_edit_sheet.dart';

/// The edit sheet's contract is narrow and easy to break: it must return
/// **only** what the user changed. The server writes one audit row per changed
/// field and drops nulls, so sending everything back would either fill the
/// audit trail with fields nobody touched or look like a save that did nothing.
void main() {
  Map<String, dynamic>? result;
  var opened = 0;

  setUp(() {
    result = null;
    opened = 0;
  });

  Widget host(List<ReviewField> fields) => MaterialApp(
        theme: AppTheme.dark,
        home: Scaffold(
          body: Builder(
            builder: (context) => Center(
              child: TextButton(
                onPressed: () async {
                  opened++;
                  result = await showReviewEditSheet(
                    context,
                    title: 'Invoice details',
                    fields: fields,
                  );
                },
                child: const Text('open'),
              ),
            ),
          ),
        ),
      );

  Future<void> open(WidgetTester tester, List<ReviewField> fields) async {
    await tester.pumpWidget(host(fields));
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    expect(opened, 1);
  }

  testWidgets('sends only the fields that were edited', (tester) async {
    await open(tester, const [
      ReviewField(
        name: 'invoice_number',
        label: 'Invoice number',
        initial: 'INV-9001',
      ),
      ReviewField(
        name: 'order_number',
        label: 'Order number',
        initial: 'PO-77',
      ),
    ]);

    await tester.enterText(find.byType(TextFormField).first, 'INV-9002');
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();

    expect(result, {'invoice_number': 'INV-9002'});
  });

  testWidgets('a field cleared to blank keeps what is already there',
      (tester) async {
    // The server drops nulls from a patch, so an empty value could never have
    // cleared the field — sending it would be a save that silently does
    // nothing.
    await open(tester, const [
      ReviewField(
        name: 'invoice_number',
        label: 'Invoice number',
        initial: 'INV-9001',
      ),
    ]);

    await tester.enterText(find.byType(TextFormField).first, '');
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();

    expect(result, isEmpty);
    expect(
      find.text('A field left blank keeps the value that is already there.'),
      findsNothing,
      reason: 'the sheet closed',
    );
  });

  testWidgets('numbers are sent as numbers, not as the text typed',
      (tester) async {
    await open(tester, const [
      ReviewField(
        name: 'net_amount',
        label: 'Net amount',
        kind: ReviewFieldKind.decimal,
        initial: 1250.75,
      ),
      ReviewField(
        name: 'item_count',
        label: 'Lines',
        kind: ReviewFieldKind.integer,
        initial: 3,
      ),
    ]);

    await tester.enterText(find.byType(TextFormField).first, '1300.5');
    await tester.enterText(find.byType(TextFormField).last, '4');
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();

    expect(result, {'net_amount': 1300.5, 'item_count': 4});
  });

  testWidgets('a whole number that is not whole is caught before it is sent',
      (tester) async {
    await open(tester, const [
      ReviewField(
        name: 'item_count',
        label: 'Lines',
        kind: ReviewFieldKind.integer,
        initial: 3,
      ),
    ]);

    // The keyboard filter blocks a decimal point, so the only way to a bad
    // value is a stray minus — either way the sheet must not close on one.
    await tester.enterText(find.byType(TextFormField).first, '4-2');
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();

    expect(find.text('Whole numbers only'), findsOneWidget);
    expect(result, isNull, reason: 'the sheet is still open');
  });

  testWidgets('a value that never had a decimal is not shown with one',
      (tester) async {
    await open(tester, const [
      ReviewField(
        name: 'quantity',
        label: 'Quantity',
        kind: ReviewFieldKind.decimal,
        initial: 10.0,
      ),
    ]);

    expect(find.text('10'), findsOneWidget);
    expect(find.text('10.0'), findsNothing);
  });

  testWidgets('a date is picked, and sent in the form the server parses',
      (tester) async {
    await open(tester, const [
      ReviewField(
        name: 'expiry_date',
        label: 'Expiry',
        kind: ReviewFieldKind.date,
      ),
    ]);

    await tester.tap(find.byType(TextFormField).first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('OK'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();

    expect(result, hasLength(1));
    expect(result!['expiry_date'], matches(RegExp(r'^\d{4}-\d{2}-\d{2}$')));
  });

  testWidgets('Save stays on screen even with a sheet full of fields',
      (tester) async {
    // A line edit carries nine fields. When the sheet sized itself to its
    // content it grew past the display and put Save below the bottom edge with
    // nothing to scroll — a bug that only showed up running on a phone.
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);

    await open(tester, const [
      ReviewField(name: 'a', label: 'Product'),
      ReviewField(name: 'b', label: 'Batch'),
      ReviewField(name: 'c', label: 'Expiry', kind: ReviewFieldKind.date),
      ReviewField(name: 'd', label: 'Quantity', kind: ReviewFieldKind.decimal),
      ReviewField(name: 'e', label: 'Free', kind: ReviewFieldKind.decimal),
      ReviewField(name: 'f', label: 'Rate', kind: ReviewFieldKind.decimal),
      ReviewField(name: 'g', label: 'MRP', kind: ReviewFieldKind.decimal),
      ReviewField(name: 'h', label: 'GST %', kind: ReviewFieldKind.decimal),
      ReviewField(name: 'i', label: 'Amount', kind: ReviewFieldKind.decimal),
    ]);

    final save = tester.getRect(find.text('Save'));
    expect(save.bottom, lessThanOrEqualTo(844));

    // And it still works from there.
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();
    expect(result, isEmpty);
  });

  testWidgets('backing out changes nothing', (tester) async {
    await open(tester, const [
      ReviewField(
        name: 'invoice_number',
        label: 'Invoice number',
        initial: 'INV-9001',
      ),
    ]);

    await tester.enterText(find.byType(TextFormField).first, 'INV-9002');
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();

    expect(result, isNull);
  });
}
