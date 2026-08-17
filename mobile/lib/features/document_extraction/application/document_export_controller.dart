import 'dart:io';
import 'dart:ui' show Rect;

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';

import 'package:nexora_mobile/core/di/capture_providers.dart';
import 'package:nexora_mobile/core/network/api_exception.dart';
import 'package:nexora_mobile/core/services/app_logger.dart';
import 'package:nexora_mobile/features/document_extraction/application/document_review_controller.dart';
import 'package:nexora_mobile/features/document_extraction/data/document_extraction_api.dart';
import 'package:nexora_mobile/features/document_extraction/domain/document_status.dart';

/// What an export did, in words the screen can show as-is.
class ExportOutcome {
  const ExportOutcome({required this.message, this.ok = true, this.filePath});

  const ExportOutcome.failed(String message)
      : this(message: message, ok: false);

  final String message;
  final bool ok;

  /// Where the workbook was written, for a follow-up "open" or re-share.
  final String? filePath;
}

/// Hands one file to the system share sheet.
typedef FileSharer = Future<void> Function(
  File file, {
  String? subject,
  Rect? sharePositionOrigin,
});

/// Where the workbook is written on its way to the share sheet, and how it is
/// handed over.
///
/// Both are platform channels, and both are behind providers for one reason:
/// an export that silently produces an unopenable file is the failure this
/// feature cannot afford, and it has to be testable without a device.
final exportDirectoryProvider = Provider<Future<Directory> Function()>(
  (ref) => getTemporaryDirectory,
);

final fileSharerProvider = Provider<FileSharer>(
  (ref) => (file, {subject, sharePositionOrigin}) => Share.shareXFiles(
        [XFile(file.path, mimeType: DocumentExportController.xlsxMimeType)],
        subject: subject,
        // Required on iPad, where a share sheet is a popover that has to be
        // anchored to something. The handoff calls out camera-less tablets as
        // review-and-export devices, so this is not a hypothetical.
        sharePositionOrigin: sharePositionOrigin,
      ),
);

final documentExportControllerProvider =
    Provider<DocumentExportController>(DocumentExportController.new);

/// Turns committed imports into a workbook and hands it to the share sheet.
///
/// The workbook is **built by the server** — `docs/Document_Extraction_Excel_Contract.md`
/// freezes five sheets, and a phone rebuilding that layout would drift from
/// the desktop export the same accountant opens. This downloads what the
/// server made and gets it off the device.
class DocumentExportController {
  DocumentExportController(this._ref);

  final Ref _ref;
  final _log = AppLogger.of('DocumentExport');

  static const String xlsxMimeType =
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';

  /// Builds one workbook covering [importIds], shares it, and marks the local
  /// rows exported.
  ///
  /// [batchIds] are the local queue rows behind those imports, when the export
  /// was started from this device. They are what lets "Free up space" reclaim
  /// the page images afterwards.
  Future<ExportOutcome> exportAndShare({
    required List<int> importIds,
    List<int> batchIds = const [],
    String? subject,
    String? fileLabel,
    Rect? sharePositionOrigin,
  }) async {
    if (importIds.isEmpty) {
      return const ExportOutcome.failed('There is nothing to export yet.');
    }

    final api = _ref.read(documentExtractionApiProvider);
    final actor = _ref.read(reviewActorProvider);

    final List<int> bytes;
    final ExportBatch batch;
    try {
      batch = await api.createExport(importIds: importIds, actor: actor);
      if (batch.exportBatchId.isEmpty) {
        return const ExportOutcome.failed(
          'The server did not return an export to download.',
        );
      }
      bytes = await api.downloadExport(batch.exportBatchId);
    } on ApiException catch (e) {
      _log.warning('Export of $importIds failed: ${e.message}');
      return ExportOutcome.failed(
        e.isNetwork
            ? 'Cannot reach the server, so no workbook was created. '
                'Try again when you are online.'
            : e.message,
      );
    }

    if (bytes.isEmpty) {
      // Distinguished from a failure: the call succeeded, so retrying will
      // produce the same empty file. Something is wrong server-side.
      return const ExportOutcome.failed('The workbook came back empty.');
    }

    final File file;
    try {
      file = await _write(bytes, fileLabel: fileLabel, count: importIds.length);
    } on FileSystemException catch (e) {
      _log.warning('Could not write the workbook: ${e.message}');
      return const ExportOutcome.failed(
        'There is not enough space to save the workbook.',
      );
    }

    // Marked before sharing: the share sheet may never come back (the user
    // switches to WhatsApp and stays there), and the export itself is already
    // done on the server. Recording it late would leave the queue claiming
    // work that is finished.
    await _markExported(batchIds);

    try {
      await _ref.read(fileSharerProvider)(
        file,
        subject: subject,
        sharePositionOrigin: sharePositionOrigin,
      );
    } on Object catch (e) {
      _log.warning('Share sheet failed: $e');
      return ExportOutcome(
        message: 'The workbook was created but could not be shared.',
        ok: false,
        filePath: file.path,
      );
    }

    return ExportOutcome(
      message: _summary(importIds.length, batch.rowCount),
      filePath: file.path,
    );
  }

  /// The line count is worth saying: it is the one number that tells the
  /// sender at a glance whether the workbook holds the invoice they meant.
  static String _summary(int invoices, int rows) {
    final lines = rows > 0 ? ' — $rows line${rows == 1 ? '' : 's'}' : '';
    return invoices == 1
        ? 'Workbook shared$lines.'
        : 'Workbook shared — $invoices invoices'
            '${rows > 0 ? ', $rows lines' : ''}.';
  }

  /// The server serves the file as `<uuid>.xlsx`. A workbook that lands in
  /// someone's chat named `4f9c…c1.xlsx` tells them nothing, so it is renamed
  /// on the way out.
  Future<File> _write(
    List<int> bytes, {
    String? fileLabel,
    required int count,
  }) async {
    final dir = await _ref.read(exportDirectoryProvider)();
    final stamp = DateTime.now();
    final date = '${stamp.year}-${_two(stamp.month)}-${_two(stamp.day)}';
    final label =
        _sanitise(fileLabel) ?? (count == 1 ? 'invoice' : '$count-invoices');
    final file = File('${dir.path}/axythic-$label-$date.xlsx');
    await file.writeAsBytes(bytes, flush: true);
    return file;
  }

  Future<void> _markExported(List<int> batchIds) async {
    if (batchIds.isEmpty) return;
    final queue = _ref.read(captureQueueRepositoryProvider);
    for (final batchId in batchIds) {
      await queue.syncStatus(batchId, DocumentStatus.exported);
      await queue.markExported(batchId);
    }
  }

  static String _two(int value) => value.toString().padLeft(2, '0');

  /// Invoice numbers routinely contain `/` and spaces, neither of which
  /// survives being part of a file name.
  static String? _sanitise(String? label) {
    if (label == null) return null;
    final cleaned = label
        .replaceAll(RegExp('[^A-Za-z0-9]+'), '-')
        .replaceAll(RegExp('^-+|-+\$'), '');
    if (cleaned.isEmpty) return null;
    // Long enough to identify the invoice, short enough to read in a file list.
    return cleaned.length <= 40 ? cleaned : cleaned.substring(0, 40);
  }
}
