import 'dart:io';
import 'dart:math';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:nexora_mobile/core/di/capture_providers.dart';
import 'package:nexora_mobile/core/services/app_logger.dart';
import 'package:nexora_mobile/features/auth/application/auth_controller.dart';
import 'package:nexora_mobile/features/document_extraction/data/capture_processor.dart';
import 'package:nexora_mobile/features/document_extraction/data/capture_queue_repository.dart';
import 'package:nexora_mobile/features/document_extraction/data/capture_storage.dart';
import 'package:nexora_mobile/features/document_extraction/domain/capture_quality.dart';

/// One page held in an in-progress capture, already on disk.
class CapturedPage {
  const CapturedPage({
    required this.filePath,
    required this.byteSize,
    required this.quality,
  });

  final String filePath;
  final int byteSize;
  final CaptureQuality quality;

  File get file => File(filePath);
}

/// The multi-page capture the user is assembling right now.
///
/// Pages are on disk from the moment the shutter fires, so this state is a
/// view over durable files rather than the only copy of the work — killing
/// the app mid-capture loses the ordering, not the photographs.
class CaptureSessionState {
  const CaptureSessionState({
    required this.sessionId,
    this.pages = const [],
    this.busy = false,
    this.error,
  });

  final String sessionId;
  final List<CapturedPage> pages;

  /// True while a shot is being processed or the batch is being committed.
  /// The shutter is disabled meanwhile so a double-tap cannot interleave two
  /// decodes.
  final bool busy;

  final String? error;

  bool get isEmpty => pages.isEmpty;
  int get pageCount => pages.length;
  int get totalBytes => pages.fold(0, (sum, p) => sum + p.byteSize);

  /// Pages the quality gate flagged, for the summary before submitting.
  int get flaggedCount =>
      pages.where((p) => p.quality.verdict.needsAttention).length;

  CaptureSessionState copyWith({
    String? sessionId,
    List<CapturedPage>? pages,
    bool? busy,
    String? error,
    bool clearError = false,
  }) {
    return CaptureSessionState(
      sessionId: sessionId ?? this.sessionId,
      pages: pages ?? this.pages,
      busy: busy ?? this.busy,
      error: clearError ? null : (error ?? this.error),
    );
  }
}

final captureSessionProvider =
    NotifierProvider<CaptureSessionController, CaptureSessionState>(
  CaptureSessionController.new,
);

/// Owns the pages of an in-progress capture and the hand-off to the upload
/// queue. Kept out of the camera screen's `State` so that committing a batch
/// is testable without a camera, and so a page survives the screen rebuilding.
class CaptureSessionController extends Notifier<CaptureSessionState> {
  final _log = AppLogger.of('CaptureSession');

  CaptureStorage get _storage => ref.read(captureStorageProvider);
  CaptureProcessor get _processor => ref.read(captureProcessorProvider);
  CaptureQueueRepository get _queue => ref.read(captureQueueRepositoryProvider);

  @override
  CaptureSessionState build() =>
      CaptureSessionState(sessionId: _newSessionId());

  /// Processes and stores one shot, returning the page so the caller can show
  /// its quality verdict. Returns null if the image could not be read.
  Future<CapturedPage?> addPage(File source) async {
    state = state.copyWith(busy: true, clearError: true);
    try {
      final bytes = await source.readAsBytes();
      final processed = await _processor.process(bytes);
      if (processed == null) {
        state = state.copyWith(
          busy: false,
          error: 'That file could not be read as an image.',
        );
        return null;
      }

      final file = await _storage.writePage(
        sessionId: state.sessionId,
        pageNumber: state.pageCount + 1,
        bytes: processed.jpegBytes,
      );

      final page = CapturedPage(
        filePath: file.path,
        byteSize: processed.byteSize,
        quality: processed.quality,
      );
      state = state.copyWith(
        pages: [...state.pages, page],
        busy: false,
      );
      _log.fine(
        'Page ${state.pageCount}: ${processed.width}x${processed.height}, '
        '${(page.byteSize / 1024).round()} KB, ${page.quality.verdict.name}',
      );
      return page;
    } on FileSystemException catch (e) {
      _log.warning('Could not store captured page: ${e.message}');
      state = state.copyWith(
        busy: false,
        error: 'There is not enough space to store this page.',
      );
      return null;
    }
  }

  /// Drops a page and its file. Used by both "retake" and the thumbnail
  /// strip's delete.
  Future<void> removePage(int index) async {
    if (index < 0 || index >= state.pages.length) return;
    final page = state.pages[index];
    final remaining = [...state.pages]..removeAt(index);
    state = state.copyWith(pages: remaining, clearError: true);
    await _storage.deletePage(page.filePath);
  }

  /// Moves a page within the invoice. Page order is the reading order the
  /// server extracts against, so line items on page 2 must not arrive first.
  void reorder(int oldIndex, int newIndex) {
    if (oldIndex == newIndex) return;
    final pages = [...state.pages];
    if (oldIndex < 0 || oldIndex >= pages.length) return;
    final page = pages.removeAt(oldIndex);
    pages.insert(newIndex.clamp(0, pages.length), page);
    state = state.copyWith(pages: pages);
  }

  /// Writes the session into the upload queue and starts a fresh one.
  ///
  /// Returns the local batch id, or null if there was nothing to submit. The
  /// upload itself is deliberately not awaited: the user is done the moment
  /// the batch is durable, and the drain runs whenever there is signal.
  Future<int?> commit() async {
    if (state.isEmpty) return null;

    final auth = ref.read(authControllerProvider);
    final tenantId = auth.user?.tenantId ?? auth.selectedStore?.tenantId;
    if (tenantId == null || tenantId.isEmpty) {
      state = state.copyWith(
        error: 'No tenant is associated with this session. Sign in again.',
      );
      return null;
    }

    state = state.copyWith(busy: true, clearError: true);
    try {
      final batchId = await _queue.enqueue(
        tenantId: tenantId,
        storeId: auth.selectedStore?.storeId,
        pages: state.pages
            .map(
              (p) => CapturePageDraft(
                filePath: p.filePath,
                byteSize: p.byteSize,
                qualityNote: p.quality.note,
              ),
            )
            .toList(growable: false),
      );
      _log.info('Queued batch $batchId with ${state.pageCount} page(s)');

      // A new session id, not a cleared list: the files stay where they are and
      // are now owned by the queue, so reusing the id would let a later
      // discard delete pages that are waiting to upload.
      state = CaptureSessionState(sessionId: _newSessionId());
      return batchId;
    } finally {
      if (state.busy) state = state.copyWith(busy: false);
    }
  }

  /// Throws the whole session away, files included.
  Future<void> discard() async {
    final sessionId = state.sessionId;
    final hadPages = state.pages.isNotEmpty;
    state = CaptureSessionState(sessionId: _newSessionId());
    if (hadPages) await _storage.discardSession(sessionId);
  }

  void clearError() {
    if (state.error != null) state = state.copyWith(clearError: true);
  }

  static String _newSessionId() {
    final stamp = DateTime.now().millisecondsSinceEpoch.toRadixString(36);
    final salt = Random().nextInt(1 << 20).toRadixString(36);
    return '${stamp}_$salt';
  }
}
