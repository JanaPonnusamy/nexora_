import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/di/capture_providers.dart';
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
  });

  const ReviewActionResult.failed(String message)
      : this(message: message, ok: false);

  /// The save was refused because unresolved errors remain. The screen offers
  /// to save anyway rather than retrying with `force` on the user's behalf —
  /// overriding validation is a decision, not a retry.
  const ReviewActionResult.needsForce(String message)
      : this(message: message, ok: false, blockedByErrors: true);

  final String message;
  final bool ok;
  final bool blockedByErrors;
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
      );

  /// Takes a line out of the invoice. One-way: the server has no endpoint that
  /// puts it back, which is why the screen confirms first.
  Future<ReviewActionResult> excludeItem(int importId, int itemId) => _edit(
        importId,
        () => _api.excludeItem(importId, itemId, actor: _actor),
        'Line removed from the invoice.',
      );

  Future<ReviewActionResult> assignSupplier(
    int importId,
    Map<String, dynamic> fields,
  ) =>
      _edit(
        importId,
        () => _api.assignSupplier(importId, fields, actor: _actor),
        'Supplier assigned.',
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
    String successMessage,
  ) async {
    try {
      await apply();
    } on ApiException catch (e) {
      _log.warning('Edit on import $importId failed: ${e.message}');
      return ReviewActionResult.failed(
        e.isNetwork
            ? 'Cannot reach the server, so the change was not saved.'
            : e.message,
      );
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
