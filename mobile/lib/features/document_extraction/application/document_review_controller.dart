import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/di/capture_providers.dart';
import 'package:nexora_mobile/core/di/outbox_providers.dart';
import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/core/services/app_logger.dart';
import 'package:nexora_mobile/features/auth/application/auth_controller.dart';
import 'package:nexora_mobile/features/document_extraction/data/document_extraction_api.dart';
import 'package:nexora_mobile/features/document_extraction/domain/document_review.dart';
import 'package:nexora_mobile/features/document_extraction/domain/document_status.dart';

/// The review payload for one import.
///
/// `autoDispose` because it is the largest object the app holds — a hundred
/// line items with their OCR text — and it is worthless the moment the user
/// leaves the screen: the server is the source of truth and every edit goes
/// straight there.
final documentReviewProvider =
    FutureProvider.autoDispose.family<DocumentReview, int>(
  (ref, importId) => ref.watch(documentExtractionApiProvider).review(importId),
);

/// Outbox kinds for the review screen's four edit operations.
///
/// String constants rather than an enum because they are persisted: a row
/// written by one build is read by the next, and renaming an enum value would
/// silently orphan a user's queued edit.
class ReviewOutboxKinds {
  ReviewOutboxKinds._();

  static const String header = 'document.header';
  static const String item = 'document.item';
  static const String exclude = 'document.exclude';
  static const String supplier = 'document.supplier';

  static const List<String> all = [header, item, exclude, supplier];
}

/// Ordering group for one document's queued edits. Everything touching import
/// 42 shares `import:42`, so those edits are applied in the order they were
/// made and never concurrently.
String reviewScope(int importId) => 'import:$importId';

/// Who the audit trail records for an edit. The server writes this into
/// `doc_import_review` per changed field, so a blank actor makes a correction
/// untraceable back to the person at the counter.
final reviewActorProvider = Provider<String?>(
  (ref) => ref.watch(authControllerProvider).user?.username,
);

final documentReviewControllerProvider =
    Provider<DocumentReviewController>(DocumentReviewController.new);

/// What a review action did, in words the screen can show as-is.
class ReviewActionResult {
  const ReviewActionResult({
    required this.message,
    this.ok = true,
    this.blockedByErrors = false,
    this.queuedOffline = false,
  });

  const ReviewActionResult.failed(String message)
      : this(message: message, ok: false);

  /// The change is safe on the device and will be sent when there is signal.
  /// Reported as a success, because from the user's side it is one: they made
  /// the correction and it is not going to be lost.
  const ReviewActionResult.queued(String message)
      : this(message: message, queuedOffline: true);

  /// The save was refused because unresolved errors remain. The screen offers
  /// to save anyway rather than retrying with `force` on the user's behalf —
  /// overriding validation is a decision, not a retry.
  const ReviewActionResult.needsForce(String message)
      : this(message: message, ok: false, blockedByErrors: true);

  final String message;
  final bool ok;
  final bool blockedByErrors;

  /// True when the change was written to the outbox rather than sent. The
  /// screen uses it to say so, and to keep showing the document as having
  /// unsent work.
  final bool queuedOffline;
}

/// Edits, re-checks and commits one import under review.
///
/// Lives outside the widget tree so the two things that are easy to get wrong
/// — re-running validation after an edit, and what a 409 on save means — are
/// testable without a screen.
class DocumentReviewController {
  DocumentReviewController(this._ref);

  final Ref _ref;
  final _log = AppLogger.of('DocumentReview');

  DocumentExtractionApi get _api => _ref.read(documentExtractionApiProvider);

  String? get _actor => _ref.read(reviewActorProvider);

  Future<ReviewActionResult> patchHeader(
    int importId,
    Map<String, dynamic> fields,
  ) =>
      _edit(
        importId,
        () => _api.patchHeader(importId, fields, actor: _actor),
        'Saved.',
        kind: ReviewOutboxKinds.header,
        payload: {'importId': importId, 'fields': fields},
        summary: 'Invoice details',
      );

  Future<ReviewActionResult> patchItem(
    int importId,
    int itemId,
    Map<String, dynamic> fields,
  ) =>
      _edit(
        importId,
        () => _api.patchItem(importId, itemId, fields, actor: _actor),
        'Line updated.',
        kind: ReviewOutboxKinds.item,
        payload: {'importId': importId, 'itemId': itemId, 'fields': fields},
        summary: 'A line on this invoice',
      );

  /// Takes a line out of the invoice. One-way: the server has no endpoint that
  /// puts it back, which is why the screen confirms first.
  Future<ReviewActionResult> excludeItem(int importId, int itemId) => _edit(
        importId,
        () => _api.excludeItem(importId, itemId, actor: _actor),
        'Line removed from the invoice.',
        kind: ReviewOutboxKinds.exclude,
        payload: {'importId': importId, 'itemId': itemId},
        summary: 'A line removed from this invoice',
      );

  Future<ReviewActionResult> assignSupplier(
    int importId,
    Map<String, dynamic> fields,
  ) =>
      _edit(
        importId,
        () => _api.assignSupplier(importId, fields, actor: _actor),
        'Supplier assigned.',
        kind: ReviewOutboxKinds.supplier,
        payload: {'importId': importId, 'fields': fields},
        summary: 'Supplier for this invoice',
      );

  /// Finalises the review, and mirrors SAVED onto the local queue row.
  ///
  /// The queue poller only follows documents the server is still *working* on,
  /// so nothing else would ever move this batch off "Ready to review" — the
  /// user would come back to a queue insisting they still had work to do.
  Future<ReviewActionResult> save(
    int importId, {
    int? batchId,
    bool force = false,
  }) async {
    try {
      await _api.save(importId, force: force, actor: _actor);
    } on ApiException catch (e) {
      if (e.statusCode == 409) {
        return const ReviewActionResult.needsForce(
          'This invoice still has errors that have not been resolved.',
        );
      }
      _log.warning('Save of import $importId failed: ${e.message}');
      return ReviewActionResult.failed(
        e.isNetwork
            ? 'Cannot reach the server, so nothing was saved. '
                'Try again when you are online.'
            : e.message,
      );
    }

    if (batchId != null) {
      await _ref
          .read(captureQueueRepositoryProvider)
          .syncStatus(batchId, DocumentStatus.saved);
    }
    _ref.invalidate(documentReviewProvider(importId));
    return ReviewActionResult(
      message: force ? 'Saved with errors overridden.' : 'Invoice saved.',
    );
  }

  /// Re-reads the payload without changing anything.
  Future<void> refresh(int importId) async {
    _ref.invalidate(documentReviewProvider(importId));
    await _ref.read(documentReviewProvider(importId).future);
  }

  /// Applies one edit, re-checks the invoice, then reloads.
  ///
  /// Re-running validation is the part that matters. The server stores
  /// `validation_status` from the last `validate` run and `save` reads that
  /// stored value — so without this, correcting the missing invoice number the
  /// findings complained about leaves the invoice still marked FAILED, and the
  /// user is asked to override an error they just fixed.
  Future<ReviewActionResult> _edit(
    int importId,
    Future<void> Function() apply,
    String successMessage, {
    required String kind,
    required Map<String, dynamic> payload,
    required String summary,
  }) async {
    try {
      await apply();
    } on ApiException catch (e) {
      // Only a *network* failure is queued. A server that refused the change —
      // a bad value, a document already saved — will refuse it again in an
      // hour, so queueing would turn a clear rejection into a change the user
      // believes is on its way and that quietly dead-letters later.
      if (e.isNetwork) {
        await _ref.read(outboxRepositoryProvider).enqueue(
              kind: kind,
              scope: reviewScope(importId),
              payload: {...payload, 'actor': _actor},
              summary: summary,
            );
        _log.info('Edit on import $importId queued offline ($kind)');
        return const ReviewActionResult.queued(
          'Saved on this device. It will sync when you are back online.',
        );
      }
      _log.warning('Edit on import $importId failed: ${e.message}');
      return ReviewActionResult.failed(e.message);
    }

    try {
      await _api.runStage(importId, DocumentStage.validate, actor: _actor);
    } on ApiException catch (e) {
      // The edit itself went through, so this is not a failure the user should
      // be asked to undo — the findings are simply one edit out of date.
      _log.warning('Re-validation of import $importId failed: ${e.message}');
    }

    _ref.invalidate(documentReviewProvider(importId));
    return ReviewActionResult(message: successMessage);
  }
}
