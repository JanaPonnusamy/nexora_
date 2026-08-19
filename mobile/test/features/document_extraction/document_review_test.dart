import 'package:flutter_test/flutter_test.dart';

import 'package:nexora_mobile/features/document_extraction/domain/document_review.dart';
import 'package:nexora_mobile/features/document_extraction/domain/document_status.dart';

void main() {
  group('DocumentStatus', () {
    test('maps every wire value the pipeline emits', () {
      expect(DocumentStatus.fromWire('UPLOADED'), DocumentStatus.uploaded);
      expect(DocumentStatus.fromWire('OCR_RUNNING'), DocumentStatus.ocrRunning);
      expect(DocumentStatus.fromWire('EXTRACTED'), DocumentStatus.extracted);
      expect(
        DocumentStatus.fromWire('REVIEW_PENDING'),
        DocumentStatus.reviewPending,
      );
      expect(DocumentStatus.fromWire('SAVED'), DocumentStatus.saved);
      expect(DocumentStatus.fromWire('FAILED'), DocumentStatus.failed);
    });

    test('is tolerant of case and whitespace', () {
      expect(
        DocumentStatus.fromWire('  review_pending '),
        DocumentStatus.reviewPending,
      );
    });

    test('an unknown status is treated as in-flight, not terminal', () {
      // A server ahead of this build must keep the client polling rather than
      // showing a wrong terminal state.
      final status = DocumentStatus.fromWire('SOME_NEW_STAGE');
      expect(status.isProcessing, isTrue);
      expect(status.isTerminal, isFalse);
    });

    test('processing and terminal are mutually exclusive', () {
      for (final status in DocumentStatus.values) {
        expect(
          status.isProcessing && status.isTerminal,
          isFalse,
          reason: status.name,
        );
      }
    });

    test('only FAILED validation blocks a save', () {
      expect(ValidationStatus.failed.blocksSave, isTrue);
      expect(ValidationStatus.warning.blocksSave, isFalse);
      expect(ValidationStatus.passed.blocksSave, isFalse);
    });
  });

  group('DocumentReview.fromJson', () {
    Map<String, dynamic> payload({
      List<Map<String, dynamic>>? items,
      Object? validation,
    }) =>
        {
          'import_id': 12,
          'status': 'REVIEW_PENDING',
          'supplier': {
            'matched_supplier_code': 'SUP01',
            'supplier_name': 'Acme Pharma',
            'is_supplier_unknown': false,
            'supplier_match_confidence': 0.94,
          },
          'header': {
            'import_id': 12,
            'invoice_number': 'INV-9001',
            'invoice_date': '2026-08-01',
            'net_amount': 1250.75,
            'ocr_confidence': 0.88,
            'page_count': 3,
          },
          'items': items ??
              [
                {
                  'item_id': 1,
                  'line_number': 1,
                  'normalized_product_name': 'Paracetamol 500mg',
                  'quantity': 10,
                  'amount': 100.5,
                  'confidence': 0.95,
                },
              ],
          if (validation != null) 'validation': validation,
        };

    test('parses header, supplier and items', () {
      final review = DocumentReview.fromJson(payload());

      expect(review.importId, 12);
      expect(review.status, DocumentStatus.reviewPending);
      expect(review.header.invoiceNumber, 'INV-9001');
      expect(review.header.invoiceDate, DateTime(2026, 8, 1));
      expect(review.header.netAmount, 1250.75);
      expect(review.supplier.supplierName, 'Acme Pharma');
      expect(review.supplier.isUnknown, isFalse);
      expect(review.items.single.productName, 'Paracetamol 500mg');
    });

    test('falls back to the raw OCR name when no normalised name exists', () {
      final review = DocumentReview.fromJson(
        payload(
          items: [
            {
              'item_id': 1,
              'line_number': 1,
              'ocr_product_name': 'PARACETMOL 500',
            },
          ],
        ),
      );
      expect(review.items.single.productName, 'PARACETMOL 500');
    });

    test('coerces numbers delivered as strings', () {
      // Raw OCR values arrive as text often enough that a strict parse would
      // blank fields the user then has to retype.
      final review = DocumentReview.fromJson(
        payload(
          items: [
            {
              'item_id': 1,
              'line_number': 1,
              'quantity': '12',
              'amount': '340.50',
              'confidence': '0.6',
            },
          ],
        ),
      );
      final item = review.items.single;
      expect(item.quantity, 12);
      expect(item.amount, 340.50);
      expect(item.isLowConfidence, isTrue);
    });

    test('excluded items are kept but not counted in the invoice', () {
      final review = DocumentReview.fromJson(
        payload(
          items: [
            {'item_id': 1, 'line_number': 1, 'amount': 100},
            {
              'item_id': 2,
              'line_number': 2,
              'amount': 50,
              'is_excluded': true,
            },
          ],
        ),
      );

      expect(review.items, hasLength(2),
          reason: 'excluded rows stay restorable');
      expect(review.includedItems, hasLength(1));
      expect(review.itemsTotal, 100);
    });

    test('counts low-confidence lines so review can be prioritised', () {
      final review = DocumentReview.fromJson(
        payload(
          items: [
            {'item_id': 1, 'line_number': 1, 'confidence': 0.99},
            {'item_id': 2, 'line_number': 2, 'confidence': 0.30},
            {'item_id': 3, 'line_number': 3, 'confidence': 0.50},
          ],
        ),
      );
      expect(review.lowConfidenceCount, 2);
    });

    test('reads validation from an object wrapper', () {
      final review = DocumentReview.fromJson(
        payload(
          validation: {
            'validation_status': 'FAILED',
            'findings': [
              {
                'severity': 'FAILED',
                'message': 'Line totals do not match net amount',
                'field': 'net_amount',
              },
            ],
          },
        ),
      );

      expect(review.validationStatus, ValidationStatus.failed);
      expect(review.canSave, isFalse);
      expect(review.findings.single.field, 'net_amount');
    });

    test('reads validation delivered as a bare array', () {
      final review = DocumentReview.fromJson(
        payload(
          validation: [
            {'severity': 'WARNING', 'message': 'Missing HSN on 2 lines'},
          ],
        ),
      );
      expect(review.findings, hasLength(1));
      expect(review.findings.single.severity, ValidationStatus.warning);
    });

    test('an empty payload parses instead of throwing', () {
      // The review screen must render something correctable, never crash.
      final review = DocumentReview.fromJson(const {});
      expect(review.items, isEmpty);
      expect(review.findings, isEmpty);
      expect(review.header.invoiceNumber, isNull);
      expect(review.supplier.isUnknown, isFalse);
    });

    test('malformed sections are ignored rather than fatal', () {
      final review = DocumentReview.fromJson({
        'import_id': 5,
        'header': 'not-an-object',
        'supplier': 42,
        'items': ['nonsense', 7],
        'validation': 'unparseable',
      });

      expect(review.importId, 5);
      expect(review.items, isEmpty);
      expect(review.findings, isEmpty);
    });

    test('blank strings become null, not empty text', () {
      final review = DocumentReview.fromJson({
        'import_id': 1,
        'header': {'import_id': 1, 'invoice_number': '   '},
      });
      expect(review.header.invoiceNumber, isNull);
    });

    test('an ERROR finding is read as an error, not as unchecked', () {
      // The import-level status is PASSED/WARNING/FAILED but a finding's own
      // severity is ERROR/WARNING. Reading ERROR as PENDING would hide the one
      // finding that blocks a save behind a neutral badge.
      final review = DocumentReview.fromJson(
        payload(
          validation: {
            'validation_status': 'FAILED',
            'findings': [
              {
                'rule_code': 'MISSING_REQUIRED_FIELD',
                'severity': 'ERROR',
                'field': 'invoice_number',
                'message': 'Invoice Number is missing.',
              },
              {
                'rule_code': 'INVALID_BATCH',
                'severity': 'WARNING',
                'item_id': 7,
                'message': 'Batch number looks invalid or missing.',
              },
            ],
          },
        ),
      );

      expect(review.errorCount, 1);
      expect(review.warningCount, 1);
      expect(review.findings.first.isError, isTrue);
      expect(review.findings.first.rule, 'MISSING_REQUIRED_FIELD');
    });

    test('findings are split between the invoice and its lines', () {
      final review = DocumentReview.fromJson(
        payload(
          validation: [
            {'severity': 'ERROR', 'message': 'Net Amount is missing.'},
            {'severity': 'WARNING', 'item_id': 2, 'message': 'Bad batch.'},
            {'severity': 'WARNING', 'item_id': 2, 'message': 'Bad expiry.'},
          ],
        ),
      );

      expect(review.headerFindings, hasLength(1));
      expect(review.findingsFor(2), hasLength(2));
      expect(review.findingsFor(99), isEmpty);
    });

    test('the preview path is read from either level of the payload', () {
      expect(
        DocumentReview.fromJson({
          ...payload(),
          'preview_image_path': '/data/previews/12_1.png',
        }).previewImagePath,
        '/data/previews/12_1.png',
      );
      expect(DocumentReview.fromJson(payload()).previewImagePath, isNull);
    });
  });

  group('DocumentItem highlights', () {
    DocumentItem item(Map<String, dynamic> fields) => DocumentItem.fromJson({
          'item_id': 1,
          'line_number': 1,
          ...fields,
        });

    test('a line with no ProductCode cannot post, whatever else is right', () {
      expect(item({'product_code': 'P-1'}).isMissingProduct, isFalse);
      expect(item({}).isMissingProduct, isTrue);
    });

    test('OCR noise is not a batch number', () {
      // The failure mode is a stray glyph, not a wrong-but-plausible value.
      expect(item({'batch_number': 'A1234'}).hasInvalidBatch, isFalse);
      expect(item({'batch_number': '--'}).hasInvalidBatch, isTrue);
      expect(item({'batch_number': '7'}).hasInvalidBatch, isTrue);
      expect(item({}).hasInvalidBatch, isTrue);
    });

    test('an unparsed expiry is a problem; no expiry at all is not', () {
      final now = DateTime(2026, 8, 16);
      expect(item({'expiry_raw': '13/25'}).hasExpiryProblem(now), isTrue);
      expect(item({}).hasExpiryProblem(now), isFalse);
    });

    test('expired stock is flagged for a person, not rejected', () {
      final now = DateTime(2026, 8, 16);
      expect(
        item({'expiry_raw': '07/26', 'expiry_date': '2026-07-31'})
            .hasExpiryProblem(now),
        isTrue,
      );
      expect(
        item({'expiry_raw': '09/26', 'expiry_date': '2026-09-30'})
            .hasExpiryProblem(now),
        isFalse,
      );
    });

    test('every problem on a line is named', () {
      final flagged = item({
        'batch_number': '.',
        'expiry_raw': 'XX/XX',
        'confidence': 0.4,
      });

      expect(
        flagged.highlights(DateTime(2026, 8, 16)),
        [
          'Missing product',
          'Low confidence',
          'Invalid batch',
          'Invalid expiry'
        ],
      );
      expect(
        item({
          'product_code': 'P-1',
          'batch_number': 'B12',
          'confidence': 0.99,
        }).highlights(DateTime(2026, 8, 16)),
        isEmpty,
      );
    });
  });

  group('DocumentReview reconciliation', () {
    DocumentReview review({
      double? netAmount,
      double? totalQuantity,
      int? itemCount,
      required List<Map<String, dynamic>> items,
    }) =>
        DocumentReview.fromJson({
          'import_id': 1,
          'header': {
            'import_id': 1,
            if (netAmount != null) 'net_amount': netAmount,
            if (totalQuantity != null) 'total_quantity': totalQuantity,
            if (itemCount != null) 'item_count': itemCount,
          },
          'items': items,
        });

    test('compares the header against what the lines actually sum to', () {
      final r = review(
        netAmount: 300,
        totalQuantity: 12,
        itemCount: 2,
        items: [
          {'item_id': 1, 'line_number': 1, 'amount': 100, 'quantity': 5},
          {'item_id': 2, 'line_number': 2, 'amount': 200, 'quantity': 7},
        ],
      );

      expect(r.reconciliation, hasLength(3));
      expect(r.reconciles, isTrue);
      expect(r.itemsTotal, 300);
      expect(r.itemsQuantity, 12);
    });

    test('excluded lines are left out of the sums', () {
      final r = review(
        netAmount: 100,
        itemCount: 1,
        items: [
          {'item_id': 1, 'line_number': 1, 'amount': 100},
          {
            'item_id': 2,
            'line_number': 2,
            'amount': 250,
            'is_excluded': true,
          },
        ],
      );

      expect(r.reconciles, isTrue);
    });

    test('a rupee of rounding balances; a real gap does not', () {
      expect(
        review(
          netAmount: 100.40,
          items: [
            {'item_id': 1, 'line_number': 1, 'amount': 100},
          ],
        ).reconciles,
        isTrue,
      );
      expect(
        review(
          netAmount: 140,
          items: [
            {'item_id': 1, 'line_number': 1, 'amount': 100},
          ],
        ).reconciliation.single.difference,
        -40,
      );
    });

    test('a line count that is one out is a mismatch, not rounding', () {
      final r = review(
        itemCount: 2,
        items: [
          {'item_id': 1, 'line_number': 1},
        ],
      );

      expect(r.reconciliation.single.balanced, isFalse);
    });

    test('a header figure the pipeline never found is not a mismatch', () {
      // It is already reported as a missing-field finding; saying it again as
      // "does not add up" would send the reviewer looking for a second problem.
      final r = review(
        items: [
          {'item_id': 1, 'line_number': 1, 'amount': 100},
        ],
      );

      expect(r.reconciliation, isEmpty);
      expect(r.reconciles, isTrue);
    });
  });
}
